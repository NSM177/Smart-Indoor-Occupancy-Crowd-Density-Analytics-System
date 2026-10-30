"""Pydantic v2 schemas for Crowd Density Analytics (Module 5)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class ZoneDensitySnapshot(BaseModel):
    zone_id: str
    zone_code: str
    zone_name: str
    person_count: int
    area_sqm: float
    max_capacity: int
    density_per_sqm: float
    capacity_ratio: float
    utilization_pct: float
    severity: str


class RoomDensityCurrentResponse(BaseModel):
    room_id: str
    room_code: str
    room_name: str
    total_count: int
    area_sqm: float
    max_capacity: int
    overall_density_per_sqm: float
    capacity_utilization_pct: float
    room_status: str
    busiest_zone: Optional[ZoneDensitySnapshot] = None
    zones: List[ZoneDensitySnapshot]
    updated_at: datetime


class DensityRecordResponse(BaseModel):
    id: int
    room_id: str
    zone_id: str
    zone_code: Optional[str] = None
    zone_name: Optional[str] = None
    person_count: int
    density_per_sqm: float
    capacity_ratio: float
    severity: str
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
