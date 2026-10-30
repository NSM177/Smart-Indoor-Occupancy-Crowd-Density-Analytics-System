"""
Module 4: Zone-based Density Analyzer (`zone_analyzer.py`).
Supports loading Polygon Zones from a JSON file (`config/zones.json`) or runtime API,
determines which zone each tracked person belongs to based on the bottom-center
foot point of their bounding box (`cv2.pointPolygonTest`), and calculates:
- Person count per zone
- Calibrated density (people / m²)
- Occupancy rate (%)
- Density level (LOW, MEDIUM, HIGH, CRITICAL)
- Average dwell time (seconds)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.core.logger import get_logger
from app.schemas.vision_schema import (
    DensityLevel,
    NormalizedPoint,
    RoomVisionConfig,
    TrackedPerson,
    VirtualLineConfig,
    ZoneConfig,
    ZoneTelemetry,
)

logger = get_logger("ai.vision.zone_analyzer")


class ZoneAnalyzer:
    """Evaluates person foot coordinates against normalized polygon zones."""

    @staticmethod
    def load_config_from_json(json_path: str | Path) -> Optional[RoomVisionConfig]:
        """Load Room, Polygon Zones, and Virtual Lines from a JSON file."""
        path = Path(json_path)
        if not path.exists():
            logger.warning("Zone configuration JSON file not found at %s", path)
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            zones: List[ZoneConfig] = []
            for z in raw.get("zones", []):
                pts = [
                    NormalizedPoint(x=float(p["x"]), y=float(p["y"]))
                    for p in z.get("polygonPoints", [])
                ]
                if len(pts) >= 3:
                    zones.append(
                        ZoneConfig(
                            id=str(z["id"]),
                            name=str(z["name"]),
                            code=str(z["code"]),
                            polygonPoints=pts,
                            areaSqm=float(z["areaSqm"]),
                            maxCapacity=int(z["maxCapacity"]),
                            warningDensityThreshold=float(
                                z.get("warningDensityThreshold", 0.35)
                            ),
                            criticalDensityThreshold=float(
                                z.get("criticalDensityThreshold", 0.50)
                            ),
                            colorHex=str(z.get("colorHex", "#3B82F6")),
                            isActive=bool(z.get("isActive", True)),
                        )
                    )

            vlines: List[VirtualLineConfig] = []
            for vl in raw.get("virtualLines", []):
                vlines.append(
                    VirtualLineConfig(
                        id=str(vl.get("id", "line-1")),
                        name=str(vl.get("name", "Entrance Line")),
                        start=NormalizedPoint(
                            x=float(vl["start"]["x"]),
                            y=float(vl["start"]["y"]),
                        ),
                        end=NormalizedPoint(
                            x=float(vl["end"]["x"]),
                            y=float(vl["end"]["y"]),
                        ),
                        inDirection=vl.get("inDirection", "DOWN"),
                    )
                )

            return RoomVisionConfig(
                roomId=str(raw.get("roomId", "default-room-01")),
                roomName=str(raw.get("roomName", "Smart Monitored Space")),
                areaSqm=float(raw.get("areaSqm", 120.0)),
                maxCapacity=int(raw.get("maxCapacity", 60)),
                warningDensityThreshold=float(
                    raw.get("warningDensityThreshold", 0.35)
                ),
                criticalDensityThreshold=float(
                    raw.get("criticalDensityThreshold", 0.50)
                ),
                hysteresisRatio=float(raw.get("hysteresisRatio", 0.10)),
                sustainViolationSec=float(raw.get("sustainViolationSec", 2.0)),
                zones=zones,
                virtualLines=vlines,
            )
        except Exception as exc:
            logger.error("Failed to parse zones JSON '%s': %s", path, exc)
            return None

    @staticmethod
    def classify_density_level(
        density: float,
        warning_threshold: float,
        critical_threshold: float,
    ) -> DensityLevel:
        if density >= critical_threshold:
            return "CRITICAL"
        if density >= warning_threshold:
            return "HIGH"
        if density >= warning_threshold * 0.5:
            return "MEDIUM"
        return "LOW"

    @classmethod
    def analyze_zones(
        cls,
        tracks: List[TrackedPerson],
        zones: List[ZoneConfig],
        frame_width: int,
        frame_height: int,
    ) -> Tuple[List[TrackedPerson], List[ZoneTelemetry]]:
        """
        Assign each TrackedPerson to the Polygon Zone containing their foot point
        and calculate calibrated density (people / m²) for every active Zone.
        """
        active_zones = [
            z for z in zones if z.isActive and len(z.polygonPoints) >= 3
        ]

        zone_contours: Dict[str, np.ndarray] = {}
        for z in active_zones:
            pts = np.array(
                [
                    [int(round(pt.x * frame_width)), int(round(pt.y * frame_height))]
                    for pt in z.polygonPoints
                ],
                dtype=np.int32,
            )
            zone_contours[z.id] = pts

        zone_assigned_tracks: Dict[str, List[TrackedPerson]] = {
            z.id: [] for z in active_zones
        }

        for person in tracks:
            fx, fy = person.footPointPx
            person.zoneId = None
            person.zoneCode = None

            for z in active_zones:
                contour = zone_contours[z.id]
                inside = cv2.pointPolygonTest(
                    contour, (float(fx), float(fy)), False
                )
                if inside >= 0:
                    person.zoneId = z.id
                    person.zoneCode = z.code
                    zone_assigned_tracks[z.id].append(person)
                    break

        zone_telemetries: List[ZoneTelemetry] = []
        for z in active_zones:
            members = zone_assigned_tracks.get(z.id, [])
            count = len(members)
            density = (
                round(count / float(z.areaSqm), 4) if z.areaSqm > 0 else 0.0
            )
            occ_rate = (
                round((count / float(z.maxCapacity)) * 100.0, 1)
                if z.maxCapacity > 0
                else 0.0
            )
            level = cls.classify_density_level(
                density,
                z.warningDensityThreshold,
                z.criticalDensityThreshold,
            )
            avg_dwell = (
                round(sum(m.dwellSec for m in members) / float(count), 1)
                if count > 0
                else 0.0
            )

            zone_telemetries.append(
                ZoneTelemetry(
                    zoneId=z.id,
                    zoneCode=z.code,
                    zoneName=z.name,
                    areaSqm=z.areaSqm,
                    maxCapacity=z.maxCapacity,
                    count=count,
                    density=density,
                    occupancyRate=occ_rate,
                    densityLevel=level,
                    warningDensityThreshold=z.warningDensityThreshold,
                    criticalDensityThreshold=z.criticalDensityThreshold,
                    avgDwellTimeSec=avg_dwell,
                )
            )

        return tracks, zone_telemetries
