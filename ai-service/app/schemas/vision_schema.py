"""
Unified Pydantic schemas for Person Detection, ByteTrack Multi-Object Tracking,
Virtual Line People Counting, Polygon Zone Density, Heatmap, Crowd Alerts, and Performance Metrics.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

DensityLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AlertSeverity = Literal["WARNING", "CRITICAL"]


class NormalizedPoint(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class RawDetection(BaseModel):
    """Single person detection output from YOLO before tracking association."""

    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in frame pixels
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_id: int = 0  # COCO class 0 = person


class VirtualLineConfig(BaseModel):
    id: str = "line-main-entrance"
    name: str = "Main Entrance Gate"
    start: NormalizedPoint
    end: NormalizedPoint
    inDirection: Literal["DOWN", "UP", "LEFT", "RIGHT"] = "DOWN"


class ZoneConfig(BaseModel):
    id: str
    name: str
    code: str
    polygonPoints: List[NormalizedPoint]
    areaSqm: float = Field(..., gt=0)
    maxCapacity: int = Field(..., ge=1)
    warningDensityThreshold: float = 0.35
    criticalDensityThreshold: float = 0.50
    colorHex: str = "#3B82F6"
    isActive: bool = True


class CameraConfig(BaseModel):
    id: str = "default"
    name: str = "Primary Camera"
    streamUrl: str = "0"
    frameWidth: int = 1280
    frameHeight: int = 720
    targetFps: int = 15
    isActive: bool = True


class RoomVisionConfig(BaseModel):
    roomId: str = "default-room-01"
    roomName: str = "Main Conference & Exhibition Hall"
    areaSqm: float = 120.0
    maxCapacity: int = 60
    warningDensityThreshold: float = 0.35
    criticalDensityThreshold: float = 0.50
    hysteresisRatio: float = 0.10
    sustainViolationSec: float = 2.0
    cameras: List[CameraConfig] = Field(default_factory=list)
    zones: List[ZoneConfig] = Field(default_factory=list)
    virtualLines: List[VirtualLineConfig] = Field(default_factory=list)


class TrackedPerson(BaseModel):
    id: int
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in pixels
    confidence: float
    footPoint: NormalizedPoint  # normalized (0..1) bottom-center of bbox
    footPointPx: Tuple[int, int]
    zoneId: Optional[str] = None
    zoneCode: Optional[str] = None
    dwellSec: float = 0.0
    isOccluded: bool = False


class LineCrossingStats(BaseModel):
    lineId: str
    lineName: str
    inCount: int = 0
    outCount: int = 0
    netFlow: int = 0


class ZoneTelemetry(BaseModel):
    zoneId: str
    zoneCode: str
    zoneName: str
    areaSqm: float = 40.0
    maxCapacity: int = 20
    count: int
    density: float
    occupancyRate: float
    densityLevel: DensityLevel
    warningDensityThreshold: float = 0.35
    criticalDensityThreshold: float = 0.50
    avgDwellTimeSec: float
    alertActive: bool = False


class EdgeCrowdAlert(BaseModel):
    alertId: str
    targetId: str  # room_id or zone_id
    targetName: str
    metricType: Literal["PERSON_COUNT", "DENSITY"]
    severity: AlertSeverity
    measuredValue: float
    thresholdValue: float
    clearThresholdValue: float
    sustainedSec: float
    message: str
    triggeredAt: str


class PerformanceMetrics(BaseModel):
    fps: float
    inferenceTimeMs: float
    processingTimeMs: float
    frameSkip: int
    inferenceResolution: Tuple[int, int]
    modelBackend: str
    totalFramesProcessed: int


class VisionTelemetryPayload(BaseModel):
    timestamp: str
    roomId: str
    roomName: str = "Main Conference & Exhibition Hall"
    cameraId: str
    fps: float
    totalCount: int
    roomAreaSqm: float = 120.0
    roomMaxCapacity: int = 60
    roomDensity: float = 0.0
    roomOccupancyRate: float = 0.0
    roomDensityLevel: DensityLevel = "LOW"
    lineCounts: List[LineCrossingStats] = Field(default_factory=list)
    tracks: List[TrackedPerson] = Field(default_factory=list)
    zones: List[ZoneTelemetry] = Field(default_factory=list)
    activeAlerts: List[EdgeCrowdAlert] = Field(default_factory=list)
    performance: Optional[PerformanceMetrics] = None
    heatmapGrid: List[List[float]] = Field(default_factory=list)
