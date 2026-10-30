"""
Pydantic v2 contracts for validating MQTT payloads from `ai-service` and `iot-service`.
Supports 100% bidirectional compatibility between `ai-service`, `iot-service`, and `backend`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MqttZoneMetricPayload(BaseModel):
    zoneId: Optional[str] = None
    zoneCode: str = "ZONE"
    zoneName: Optional[str] = None
    count: int = Field(default=0, ge=0)
    areaSqm: float = Field(default=10.0, gt=0.0)
    maxCapacity: int = Field(default=10, ge=1)
    densityPerSqm: float = Field(default=0.0, ge=0.0)
    capacityRatio: float = Field(default=0.0, ge=0.0)
    severity: str = Field(default="NORMAL")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_zone_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "personCount" in out and "count" not in out:
            out["count"] = out["personCount"]
        if "density" in out and "densityPerSqm" not in out:
            out["densityPerSqm"] = out["density"]
        if "occupancyRate" in out and "capacityRatio" not in out:
            rate = float(out["occupancyRate"] or 0.0)
            out["capacityRatio"] = round(rate / 100.0, 4) if rate > 1.0 else rate
        if "densityLevel" in out and "severity" not in out:
            lvl = str(out["densityLevel"]).upper()
            if lvl == "CRITICAL":
                out["severity"] = "CRITICAL"
            elif lvl in ("HIGH", "WARNING"):
                out["severity"] = "WARNING"
            else:
                out["severity"] = "NORMAL"
        return out


class MqttAlertPayload(BaseModel):
    room_id: Optional[str] = None
    roomId: Optional[str] = None
    alertType: str = Field(default="CROWD_DENSITY_THRESHOLD")
    severity: str = Field(default="WARNING")
    status: str = Field(default="ACTIVE")
    zoneCode: Optional[str] = None
    personCount: int = Field(default=0, ge=0)
    densityValue: float = Field(default=0.0, ge=0.0)
    thresholdValue: float = Field(default=0.0, ge=0.0)
    message: str = Field(default="Crowd threshold alert")
    timestamp: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_alert_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "metricType" in out and "alertType" not in out:
            out["alertType"] = str(out["metricType"])
        if "measuredValue" in out and "densityValue" not in out:
            out["densityValue"] = float(out["measuredValue"] or 0.0)
        return out


class MqttAiTelemetryPayload(BaseModel):
    """Contract for `ai/rooms/{roomId}/telemetry`."""

    roomId: str
    timestamp: str
    frameIndex: int = Field(default=0, ge=0)
    fps: float = Field(default=0.0, ge=0.0)
    totalCount: int = Field(default=0, ge=0)
    inCount: int = Field(default=0, ge=0)
    outCount: int = Field(default=0, ge=0)
    overallDensity: float = Field(default=0.0, ge=0.0)
    capacityRatio: float = Field(default=0.0, ge=0.0)
    roomStatus: str = Field(default="NORMAL")
    zones: List[MqttZoneMetricPayload] = Field(default_factory=list)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    heatmapGrid: Optional[List[List[float]]] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_ai_telemetry(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "roomDensity" in out and "overallDensity" not in out:
            out["overallDensity"] = float(out["roomDensity"] or 0.0)
        if "roomOccupancyRate" in out and "capacityRatio" not in out:
            rate = float(out["roomOccupancyRate"] or 0.0)
            out["capacityRatio"] = round(rate / 100.0, 4) if rate > 1.0 else rate
        if "roomDensityLevel" in out and "roomStatus" not in out:
            lvl = str(out["roomDensityLevel"]).upper()
            if lvl == "CRITICAL":
                out["roomStatus"] = "CRITICAL"
            elif lvl in ("HIGH", "WARNING"):
                out["roomStatus"] = "WARNING"
            else:
                out["roomStatus"] = "NORMAL"
        if "lineCounts" in out and isinstance(out["lineCounts"], list) and out["lineCounts"]:
            if "inCount" not in out:
                out["inCount"] = sum(int(lc.get("inCount", 0)) for lc in out["lineCounts"] if isinstance(lc, dict))
            if "outCount" not in out:
                out["outCount"] = sum(int(lc.get("outCount", 0)) for lc in out["lineCounts"] if isinstance(lc, dict))
        if "activeAlerts" in out and "alerts" not in out:
            out["alerts"] = out["activeAlerts"]
        return out


class MqttCountPayload(BaseModel):
    """Contract for `occupancy/{room}/count`."""

    room_id: str
    timestamp: Optional[str] = None
    current_count: int = Field(..., ge=0)
    in_count: int = Field(default=0, ge=0)
    out_count: int = Field(default=0, ge=0)
    max_capacity: Optional[int] = Field(default=None, ge=1)
    capacity_ratio: Optional[float] = Field(default=None, ge=0.0)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_count_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "roomId" in out and "room_id" not in out:
            out["room_id"] = out["roomId"]
        if "totalCount" in out and "current_count" not in out:
            out["current_count"] = out["totalCount"]
        elif "count" in out and "current_count" not in out:
            out["current_count"] = out["count"]
        if "inCount" in out and "in_count" not in out:
            out["in_count"] = out["inCount"]
        if "outCount" in out and "out_count" not in out:
            out["out_count"] = out["outCount"]
        if "maxCapacity" in out and "max_capacity" not in out:
            out["max_capacity"] = out["maxCapacity"]
        if "occupancyRate" in out and "capacity_ratio" not in out:
            rate = float(out["occupancyRate"] or 0.0)
            out["capacity_ratio"] = round(rate / 100.0, 4) if rate > 1.0 else rate
        return out


class MqttDensityPayload(BaseModel):
    """Contract for `occupancy/{room}/density`."""

    room_id: str
    timestamp: Optional[str] = None
    overall_density: float = Field(..., ge=0.0)
    area_sqm: Optional[float] = Field(default=None, gt=0.0)
    alert_level: str = Field(default="NORMAL")
    zones: List[MqttZoneMetricPayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_density_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "roomId" in out and "room_id" not in out:
            out["room_id"] = out["roomId"]
        if "roomDensity" in out and "overall_density" not in out:
            out["overall_density"] = out["roomDensity"]
        elif "density" in out and "overall_density" not in out:
            out["overall_density"] = out["density"]
        if "densityLevel" in out and "alert_level" not in out:
            lvl = str(out["densityLevel"]).upper()
            if lvl == "CRITICAL":
                out["alert_level"] = "CRITICAL"
            elif lvl in ("HIGH", "WARNING"):
                out["alert_level"] = "WARNING"
            else:
                out["alert_level"] = "NORMAL"
        return out


class MqttDeviceStatusPayload(BaseModel):
    """Contract for `occupancy/{room}/device/status` and `iot/devices/{deviceId}/status`."""

    deviceId: str
    roomId: Optional[str] = None
    timestamp: Optional[str] = None
    status: str = Field(default="ONLINE")
    ledState: str = Field(default="GREEN")
    buzzerActive: bool = Field(default=False)
    autoMode: bool = Field(default=True)
    personCount: int = Field(default=0, ge=0)
    density: float = Field(default=0.0, ge=0.0)
    gpioMode: Optional[str] = Field(default="SIMULATION")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_device_status(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "led" in out and "ledState" not in out:
            out["ledState"] = out["led"]
        elif isinstance(out.get("gpioState"), dict) and "ledState" not in out:
            out["ledState"] = out["gpioState"].get("led", "GREEN")
        if "buzzer" in out and "buzzerActive" not in out:
            out["buzzerActive"] = bool(out["buzzer"])
        elif isinstance(out.get("gpioState"), dict) and "buzzerActive" not in out:
            out["buzzerActive"] = bool(out["gpioState"].get("buzzer", False))
        if "simulationMode" in out and "gpioMode" not in out:
            out["gpioMode"] = "SIMULATION" if out["simulationMode"] else "HARDWARE_BCM"
        if isinstance(out.get("occupancyMetrics"), dict):
            metrics = out["occupancyMetrics"]
            if "currentCount" in metrics and "personCount" not in out:
                out["personCount"] = int(metrics["currentCount"] or 0)
            if "currentDensity" in metrics and "density" not in out:
                out["density"] = float(metrics["currentDensity"] or 0.0)
        return out
