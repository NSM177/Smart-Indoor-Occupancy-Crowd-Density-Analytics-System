"""Pydantic v2 schemas for Alert Management (Module 6)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    id: str
    room_id: str
    zone_id: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    person_count: int
    density_value: float
    threshold_value: float
    is_acknowledged: bool
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    triggered_at: datetime

    # CamelCase compatibility for Next.js Frontend
    roomId: Optional[str] = None
    zoneId: Optional[str] = None
    alertType: Optional[str] = None
    personCount: Optional[int] = None
    densityValue: Optional[float] = None
    thresholdValue: Optional[float] = None
    isAcknowledged: Optional[bool] = None
    isResolved: Optional[bool] = None
    triggeredAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm_alert(cls, alert) -> "AlertResponse":
        return cls(
            id=alert.id,
            room_id=alert.room_id,
            zone_id=alert.zone_id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
            person_count=alert.person_count,
            density_value=alert.density_value,
            threshold_value=alert.threshold_value,
            is_acknowledged=alert.is_acknowledged,
            acknowledged_by=alert.acknowledged_by,
            acknowledged_at=alert.acknowledged_at,
            is_resolved=alert.is_resolved,
            resolved_at=alert.resolved_at,
            triggered_at=alert.triggered_at,
            roomId=alert.room_id,
            zoneId=alert.zone_id,
            alertType=alert.alert_type,
            personCount=alert.person_count,
            densityValue=alert.density_value,
            thresholdValue=alert.threshold_value,
            isAcknowledged=alert.is_acknowledged,
            isResolved=alert.is_resolved,
            triggeredAt=alert.triggered_at,
        )
