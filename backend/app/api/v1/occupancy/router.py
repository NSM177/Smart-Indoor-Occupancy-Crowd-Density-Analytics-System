"""
Modules 4 & 5 Router: Room Occupancy & Crowd Density Analytics.
Endpoints:
- `GET /api/v1/rooms/{room_id}/occupancy/current`
- `GET /api/v1/rooms/{room_id}/occupancy/history`
- `GET /api/v1/rooms/{room_id}/density/current`
- `GET /api/v1/rooms/{room_id}/density/history`
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.density import (
    DensityRecordResponse,
    RoomDensityCurrentResponse,
    ZoneDensitySnapshot,
)
from app.schemas.occupancy import (
    OccupancyCurrentResponse,
    OccupancyRecordResponse,
)
from app.services.business_services import DensityService, OccupancyService

router = APIRouter(tags=["Occupancy & Density Analytics"])


@router.get(
    "/occupancy/current",
    response_model=OccupancyCurrentResponse,
)
def get_occupancy_current_query(
    room_id: str = Query(default="room1"),
    db: Session = Depends(get_db),
) -> OccupancyCurrentResponse:
    return OccupancyService(db).get_current_occupancy(room_id)


@router.get(
    "/occupancy/zones",
    response_model=List[ZoneDensitySnapshot],
)
def get_occupancy_zones_query(
    room_id: str = Query(default="room1"),
    db: Session = Depends(get_db),
) -> List[ZoneDensitySnapshot]:
    return DensityService(db).get_current_density(room_id).zones


@router.get(
    "/rooms/{room_id}/occupancy/current",
    response_model=OccupancyCurrentResponse,
)
def get_room_occupancy_current(
    room_id: str,
    db: Session = Depends(get_db),
) -> OccupancyCurrentResponse:
    return OccupancyService(db).get_current_occupancy(room_id)


@router.get(
    "/rooms/{room_id}/occupancy/history",
    response_model=List[OccupancyRecordResponse],
)
def get_room_occupancy_history(
    room_id: str,
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> List[OccupancyRecordResponse]:
    return OccupancyService(db).get_occupancy_history(
        room_identifier=room_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )


@router.get(
    "/rooms/{room_id}/density/current",
    response_model=RoomDensityCurrentResponse,
)
def get_room_density_current(
    room_id: str,
    db: Session = Depends(get_db),
) -> RoomDensityCurrentResponse:
    return DensityService(db).get_current_density(room_id)


@router.get(
    "/rooms/{room_id}/density/history",
    response_model=List[DensityRecordResponse],
)
def get_room_density_history(
    room_id: str,
    zone_id: Optional[str] = Query(default=None),
    start_time: Optional[datetime] = Query(default=None),
    end_time: Optional[datetime] = Query(default=None),
    limit: int = Query(default=300, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> List[DensityRecordResponse]:
    return DensityService(db).get_density_history(
        room_identifier=room_id,
        zone_id=zone_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
