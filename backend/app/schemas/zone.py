"""Pydantic v2 schemas for Polygon Zone Management (Module 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Point2D(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class ZoneCreateRequest(BaseModel):
    room_id: Optional[str] = Field(default=None, alias="roomId")
    name: str = Field(..., min_length=1, max_length=80)
    code: str = Field(..., min_length=1, max_length=32)
    polygon_coordinates: List[Point2D] = Field(
        ..., min_length=3, alias="polygonCoordinates"
    )
    area_sqm: float = Field(..., gt=0.5, alias="areaSqm")
    max_capacity: int = Field(..., ge=1, alias="maxCapacity")
    warning_density: float = Field(
        default=0.50, ge=0.05, le=10.0, alias="warningDensity"
    )
    critical_density: float = Field(
        default=0.80, ge=0.05, le=10.0, alias="criticalDensity"
    )
    color_hex: str = Field(default="#3B82F6", alias="colorHex")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("polygon_coordinates")
    @classmethod
    def validate_polygon(cls, points: List[Point2D]) -> List[Point2D]:
        if len(points) < 3:
            raise ValueError("A polygon zone requires at least 3 vertices.")
        return points


class ZoneUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    polygon_coordinates: Optional[List[Point2D]] = Field(
        default=None, min_length=3, alias="polygonCoordinates"
    )
    area_sqm: Optional[float] = Field(default=None, gt=0.5, alias="areaSqm")
    max_capacity: Optional[int] = Field(default=None, ge=1, alias="maxCapacity")
    warning_density: Optional[float] = Field(
        default=None, ge=0.05, le=10.0, alias="warningDensity"
    )
    critical_density: Optional[float] = Field(
        default=None, ge=0.05, le=10.0, alias="criticalDensity"
    )
    color_hex: Optional[str] = Field(default=None, alias="colorHex")

    model_config = ConfigDict(populate_by_name=True)


class ZoneResponse(BaseModel):
    id: str
    room_id: str
    name: str
    code: str
    polygon_coordinates: List[Dict[str, float]]
    area_sqm: float
    max_capacity: int
    warning_density: float
    critical_density: float
    color_hex: str
    created_at: datetime
    updated_at: datetime

    # CamelCase compatibility fields for Frontend
    roomId: Optional[str] = None
    polygonCoordinates: Optional[List[Dict[str, float]]] = None
    areaSqm: Optional[float] = None
    maxCapacity: Optional[int] = None
    warningDensity: Optional[float] = None
    criticalDensity: Optional[float] = None
    colorHex: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm_zone(cls, zone) -> "ZoneResponse":
        return cls(
            id=zone.id,
            room_id=zone.room_id,
            name=zone.name,
            code=zone.code,
            polygon_coordinates=zone.polygon_coordinates,
            area_sqm=zone.area_sqm,
            max_capacity=zone.max_capacity,
            warning_density=zone.warning_density,
            critical_density=zone.critical_density,
            color_hex=zone.color_hex,
            created_at=zone.created_at,
            updated_at=zone.updated_at,
            roomId=zone.room_id,
            polygonCoordinates=zone.polygon_coordinates,
            areaSqm=zone.area_sqm,
            maxCapacity=zone.max_capacity,
            warningDensity=zone.warning_density,
            criticalDensity=zone.critical_density,
            colorHex=zone.color_hex,
        )
