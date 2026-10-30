"""Pydantic v2 schemas for Room Management (Module 2)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.zone import ZoneResponse


class RoomCreateRequest(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(default=None)
    area_sqm: float = Field(..., gt=1.0, alias="areaSqm")
    max_capacity: int = Field(..., ge=1, alias="maxCapacity")
    warning_threshold_ratio: float = Field(
        default=0.75, ge=0.1, le=1.0, alias="warningThresholdRatio"
    )
    critical_density_per_sqm: float = Field(
        default=0.80, ge=0.05, le=10.0, alias="criticalDensityPerSqm"
    )
    is_active: bool = Field(default=True, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)


class RoomUpdateRequest(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=64)
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    description: Optional[str] = Field(default=None)
    area_sqm: Optional[float] = Field(default=None, gt=1.0, alias="areaSqm")
    max_capacity: Optional[int] = Field(default=None, ge=1, alias="maxCapacity")
    warning_threshold_ratio: Optional[float] = Field(
        default=None, ge=0.1, le=1.0, alias="warningThresholdRatio"
    )
    critical_density_per_sqm: Optional[float] = Field(
        default=None, ge=0.05, le=10.0, alias="criticalDensityPerSqm"
    )
    is_active: Optional[bool] = Field(default=None, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)


class RoomResponse(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    area_sqm: float
    max_capacity: int
    warning_threshold_ratio: float
    critical_density_per_sqm: float
    is_active: bool
    created_at: datetime
    updated_at: datetime
    zones: List[ZoneResponse] = Field(default_factory=list)

    # CamelCase compatibility fields for Frontend Dashboard
    areaSqm: Optional[float] = None
    maxCapacity: Optional[int] = None
    warningThresholdRatio: Optional[float] = None
    criticalDensityPerSqm: Optional[float] = None
    isActive: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm_room(cls, room) -> "RoomResponse":
        zones_out = [ZoneResponse.from_orm_zone(z) for z in (room.zones or [])]
        return cls(
            id=room.id,
            code=room.code,
            name=room.name,
            description=room.description,
            area_sqm=room.area_sqm,
            max_capacity=room.max_capacity,
            warning_threshold_ratio=room.warning_threshold_ratio,
            critical_density_per_sqm=room.critical_density_per_sqm,
            is_active=room.is_active,
            created_at=room.created_at,
            updated_at=room.updated_at,
            zones=zones_out,
            areaSqm=room.area_sqm,
            maxCapacity=room.max_capacity,
            warningThresholdRatio=room.warning_threshold_ratio,
            criticalDensityPerSqm=room.critical_density_per_sqm,
            isActive=room.is_active,
        )
