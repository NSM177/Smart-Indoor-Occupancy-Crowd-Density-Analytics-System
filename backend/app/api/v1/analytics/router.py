"""
Module 8 Router: Historical Analytics, Peak Hours & Short-Term Crowd Forecasting.
Endpoints:
- `GET /api/v1/analytics/overview`
- `GET /api/v1/analytics/peak-hours`
- `GET /api/v1/analytics/occupancy`
- `GET /api/v1/analytics/density`
- `GET /api/v1/analytics/forecast`
Plus Frontend compatibility aliases under `/api/v1/analytics/rooms/{room_id}/...`
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.engine import AnalyticsEngine
from app.core.config import settings
from app.database.session import get_db
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    ForecastResponse,
    PeakHourEntry,
)
from app.schemas.occupancy import OccupancyRecordResponse
from app.services.business_services import (
    DensityService,
    OccupancyService,
    RoomService,
)

router = APIRouter(prefix="/analytics", tags=["Historical Analytics & Forecasting"])


def _resolve_target_room(
    db: Session, room_id: Optional[str], roomId: Optional[str]
):
    target = room_id or roomId or settings.INITIAL_ROOM_CODE
    return RoomService(db).get_room_entity(target)


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    room_id: Optional[str] = Query(default=None),
    roomId: Optional[str] = Query(default=None),
    hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
) -> AnalyticsOverviewResponse:
    room = _resolve_target_room(db, room_id, roomId)
    return AnalyticsEngine(db).get_overview(room, hours=hours)


@router.get("/peak-hours", response_model=List[PeakHourEntry])
def get_analytics_peak_hours(
    room_id: Optional[str] = Query(default=None),
    roomId: Optional[str] = Query(default=None),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> List[PeakHourEntry]:
    room = _resolve_target_room(db, room_id, roomId)
    return AnalyticsEngine(db).get_peak_hours(room, days=days)


@router.get("/occupancy")
def get_analytics_occupancy(
    room_id: Optional[str] = Query(default=None),
    roomId: Optional[str] = Query(default=None),
    granularity: str = Query(default="hourly", pattern="^(hourly|daily|raw)$"),
    hours: int = Query(default=24, ge=1, le=720),
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    room = _resolve_target_room(db, room_id, roomId)
    engine = AnalyticsEngine(db)
    if granularity == "daily":
        series = [p.model_dump() for p in engine.get_daily_series(room, days=days)]
    elif granularity == "raw":
        records = OccupancyService(db).get_occupancy_history(
            room.id, limit=limit
        )
        series = [r.model_dump() for r in records]
    else:
        series = [p.model_dump() for p in engine.get_hourly_series(room, hours=hours)]

    return {
        "room_id": room.id,
        "room_code": room.code,
        "granularity": granularity,
        "count": len(series),
        "series": series,
    }


@router.get("/density")
def get_analytics_density(
    room_id: Optional[str] = Query(default=None),
    roomId: Optional[str] = Query(default=None),
    zone_id: Optional[str] = Query(default=None),
    granularity: str = Query(default="hourly", pattern="^(hourly|daily|raw)$"),
    hours: int = Query(default=24, ge=1, le=720),
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    room = _resolve_target_room(db, room_id, roomId)
    engine = AnalyticsEngine(db)
    current_density = DensityService(db).get_current_density(room.id)
    if granularity == "daily":
        series = [p.model_dump() for p in engine.get_daily_series(room, days=days)]
    elif granularity == "raw":
        recs = DensityService(db).get_density_history(
            room.id, zone_id=zone_id, limit=limit
        )
        series = [r.model_dump() for r in recs]
    else:
        series = [p.model_dump() for p in engine.get_hourly_series(room, hours=hours)]

    return {
        "room_id": room.id,
        "room_code": room.code,
        "granularity": granularity,
        "current": current_density.model_dump(),
        "series": series,
    }


@router.get("/forecast", response_model=ForecastResponse)
def get_analytics_forecast(
    room_id: Optional[str] = Query(default=None),
    roomId: Optional[str] = Query(default=None),
    horizon_minutes: int = Query(default=30, ge=5, le=120),
    horizonMinutes: Optional[int] = Query(default=None, ge=5, le=120),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    room = _resolve_target_room(db, room_id, roomId)
    horizon = horizonMinutes if horizonMinutes is not None else horizon_minutes
    return AnalyticsEngine(db).get_forecast(room, horizon_minutes=horizon)


# --- Frontend Compatibility Aliases (`/api/v1/analytics/rooms/{room_id}/...`) ---

@router.get(
    "/rooms/{room_id}/history",
    response_model=List[OccupancyRecordResponse],
)
def get_room_history_alias(
    room_id: str,
    limit: int = Query(default=120, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> List[OccupancyRecordResponse]:
    return OccupancyService(db).get_occupancy_history(room_id, limit=limit)


@router.get(
    "/rooms/{room_id}/peak-hours",
    response_model=List[PeakHourEntry],
)
def get_room_peak_hours_alias(
    room_id: str,
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> List[PeakHourEntry]:
    room = RoomService(db).get_room_entity(room_id)
    return AnalyticsEngine(db).get_peak_hours(room, days=days)


@router.get(
    "/rooms/{room_id}/forecast",
    response_model=ForecastResponse,
)
def get_room_forecast_alias(
    room_id: str,
    horizonMinutes: int = Query(default=30, ge=5, le=120),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    room = RoomService(db).get_room_entity(room_id)
    return AnalyticsEngine(db).get_forecast(room, horizon_minutes=horizonMinutes)
