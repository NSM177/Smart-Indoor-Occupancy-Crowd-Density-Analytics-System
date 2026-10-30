"""
Frame Annotator for Smart Indoor Occupancy & Crowd Density Analytics.
Renders:
- Polygon Zones (with color, live count, calibrated density people/m² & alert badge)
- Virtual Counting Lines (with IN / OUT counters)
- Person Bounding Boxes + Confidence Score + ByteTrack ID + Dwell Time
- Optional Density Heatmap overlay
- Top HUD status bar with FPS, Inference latency (ms), Processing time (ms), and Active Alerts
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.schemas.vision_schema import (
    EdgeCrowdAlert,
    LineCrossingStats,
    PerformanceMetrics,
    TrackedPerson,
    VirtualLineConfig,
    ZoneConfig,
    ZoneTelemetry,
)
from app.vision.heatmap_generator import HeatmapGenerator


def hex_to_bgr(hex_str: str) -> Tuple[int, int, int]:
    """Convert '#RRGGBB' hex color string to OpenCV (B, G, R) tuple."""
    clean = hex_str.lstrip("#")
    if len(clean) != 6:
        return (246, 130, 59)
    try:
        r = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        b = int(clean[4:6], 16)
        return (b, g, r)
    except ValueError:
        return (246, 130, 59)


class FrameAnnotator:
    """Renders real-time visual overlays onto camera frames."""

    @staticmethod
    def annotate(
        frame: np.ndarray,
        tracks: List[TrackedPerson],
        zones: List[ZoneConfig],
        zone_telemetries: List[ZoneTelemetry],
        heatmap_gen: HeatmapGenerator,
        fps: float,
        room_name: str,
        virtual_lines: Optional[List[VirtualLineConfig]] = None,
        line_stats: Optional[List[LineCrossingStats]] = None,
        active_alerts: Optional[List[EdgeCrowdAlert]] = None,
        performance: Optional[PerformanceMetrics] = None,
        overlay_zones: bool = True,
        overlay_heatmap: bool = False,
    ) -> np.ndarray:
        output = frame.copy()
        height, width = output.shape[:2]

        # 1. Optional Density Heatmap layer
        if overlay_heatmap:
            output = heatmap_gen.render_Overlay(output, alpha=0.45)

        zone_telemetry_map: Dict[str, ZoneTelemetry] = {
            zt.zoneId: zt for zt in zone_telemetries
        }

        # 2. Polygon Zones overlay
        if overlay_zones and zones:
            poly_layer = output.copy()
            for z in zones:
                if not z.isActive or len(z.polygonPoints) < 3:
                    continue
                pts = np.array(
                    [
                        [int(p.x * width), int(p.y * height)]
                        for p in z.polygonPoints
                    ],
                    dtype=np.int32,
                )
                zt = zone_telemetry_map.get(z.id)
                level = zt.densityLevel if zt else "LOW"

                if level == "CRITICAL":
                    bgr = (48, 48, 239)  # Red
                elif level == "HIGH":
                    bgr = (11, 158, 245)  # Amber/Orange
                else:
                    bgr = hex_to_bgr(z.colorHex)

                cv2.fillPoly(poly_layer, [pts], bgr)
                cv2.polylines(
                    output, [pts], isClosed=True, color=bgr, thickness=2
                )

                anchor_x = int(pts[0][0])
                anchor_y = max(48, int(pts[0][1]) + 24)
                count_val = zt.count if zt else 0
                density_val = zt.density if zt else 0.0
                label = (
                    f"{z.code}: {count_val}/{z.maxCapacity}p "
                    f"({density_val:.2f}/m2) [{level}]"
                )

                (tw, th), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1
                )
                cv2.rectangle(
                    output,
                    (anchor_x, anchor_y - th - 8),
                    (anchor_x + tw + 12, anchor_y + 4),
                    bgr,
                    -1,
                )
                cv2.putText(
                    output,
                    label,
                    (anchor_x + 6, anchor_y - 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.50,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

            output = cv2.addWeighted(poly_layer, 0.18, output, 0.82, 0)

        # 3. Virtual Counting Lines overlay (IN / OUT)
        if virtual_lines:
            lstat_map = {ls.lineId: ls for ls in (line_stats or [])}
            for vl in virtual_lines:
                x1, y1 = int(vl.start.x * width), int(vl.start.y * height)
                x2, y2 = int(vl.end.x * width), int(vl.end.y * height)
                cv2.line(output, (x1, y1), (x2, y2), (0, 215, 255), 3)
                cv2.circle(output, (x1, y1), 5, (0, 215, 255), -1)
                cv2.circle(output, (x2, y2), 5, (0, 215, 255), -1)

                st = lstat_map.get(vl.id)
                in_c = st.inCount if st else 0
                out_c = st.outCount if st else 0
                line_label = f"{vl.name}: IN={in_c} | OUT={out_c}"
                mx, my = int((x1 + x2) * 0.5), max(48, int((y1 + y2) * 0.5) - 8)
                cv2.putText(
                    output,
                    line_label,
                    (mx - 60, my),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (0, 215, 255),
                    2,
                    cv2.LINE_AA,
                )

        # 4. Person Bounding Boxes, Confidence Score, Track ID, Dwell Time & Foot Point
        for person in tracks:
            x1, y1, x2, y2 = person.bbox
            fx, fy = person.footPointPx
            box_color = (129, 185, 16) if person.zoneId else (235, 168, 52)

            cv2.rectangle(output, (x1, y1), (x2, y2), box_color, 2)
            cv2.circle(output, (fx, fy), 5, (0, 255, 255), -1)

            tag = (
                f"ID #{person.id} ({person.confidence:.2f}) | "
                f"{person.dwellSec:.0f}s"
            )
            if person.zoneCode:
                tag += f" [{person.zoneCode}]"

            (tw, th), _ = cv2.getTextSize(
                tag, cv2.FONT_HERSHEY_SIMPLEX, 0.46, 1
            )
            cv2.rectangle(
                output,
                (x1, max(0, y1 - th - 8)),
                (x1 + tw + 8, y1),
                box_color,
                -1,
            )
            cv2.putText(
                output,
                tag,
                (x1 + 4, max(12, y1 - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        # 5. Top HUD status bar (with Performance & Alert summary)
        cv2.rectangle(output, (0, 0), (width, 38), (15, 23, 42), -1)
        inf_ms = performance.inferenceTimeMs if performance else 0.0
        proc_ms = performance.processingTimeMs if performance else 0.0
        alerts_cnt = len(active_alerts) if active_alerts else 0

        hud_text = (
            f"{room_name} | People: {len(tracks)} | "
            f"FPS: {fps:.1f} (Inf: {inf_ms:.1f}ms, Proc: {proc_ms:.1f}ms) | "
            f"Alerts: {alerts_cnt}"
        )
        cv2.putText(
            output,
            hud_text,
            (14, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (248, 250, 252) if alerts_cnt == 0 else (110, 110, 255),
            1,
            cv2.LINE_AA,
        )

        return output
