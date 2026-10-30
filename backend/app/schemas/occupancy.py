"""Pydantic v2 schemas for Occupancy Management (Module 4)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class OccupancyCurrentResponse(BaseModel):
    room_id: str
    room_code: str
    room_name: str
    current_count: int
    in_count: int
    out_count: int
    max_capacity: int
    capacity_ratio: float
    overall_density: float
    room_status: str
    inference_fps: Optional[float] = None
    updated_at: datetime

    # CamelCase compatibility
    roomId: Optional[str] = None
    totalCount: Optional[int] = None
    inCount: Optional[int] = None
    outCount: Optional[int] = None
    maxCapacity: Optional[int] = None
    capacityRatio: Optional[float] = None
    overallDensity: Optional[float] = None
    roomStatus: Optional[str] = None


class OccupancyRecordResponse(BaseModel):
    id: int
    room_id: str
    device_id: Optional[str] = None
    total_count: int
    in_count: int
    out_count: int
    overall_density: float
    capacity_ratio: float
    room_status: str
    inference_fps: Optional[float] = None
    recorded_at: datetime

    # CamelCase compatibility
    roomId: Optional[str] = None
    totalCount: Optional[int] = None
    inCount: Optional[int] = None
    outCount: Optional[int] = None
    overallDensity: Optional[float] = None
    capacityRatio: Optional[float] = None
    recordedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm_record(cls, rec) -> "OccupancyRecordResponse":
        return cls(
            id=rec.id,
            room_id=rec.room_id,
            device_id=rec.device_id,
            total_count=rec.total_count,
            in_count=rec.in_count,
            out_count=rec.out_count,
            overall_density=rec.overall_density,
            capacity_ratio=rec.capacity_ratio,
            room_status=rec.room_status,
            inference_fps=rec.inference_fps,
            recorded_at=rec.recorded_at,
            roomId=rec.room_id,
            totalCount=rec.total_count,
            inCount=rec.in_count,
            outCount=rec.out_count,
            overallDensity=rec.overall_density,
            capacityRatio=rec.capacity_ratio,
            recordedAt=rec.recorded_at,
        )
