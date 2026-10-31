"""
Module 3 Router: Polygon Zone Management.
Supports both:
- `/api/v1/rooms/{room_id}/zones` (RESTful nested resource)
- `/api/v1/zones/{zone_id}` (Direct zone operations & Frontend aliases)
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_operator_or_admin
from app.database.session import get_db
from app.models.entities import User
from app.schemas.zone import (
    ZoneCreateRequest,
    ZoneResponse,
    ZoneUpdateRequest,
)
from app.services.business_services import ZoneService

router = APIRouter(tags=["Zone Management"])


@router.get("/rooms/{room_id}/zones", response_model=List[ZoneResponse])
def list_room_zones(
    room_id: str,
    db: Session = Depends(get_db),
) -> List[ZoneResponse]:
    return ZoneService(db).list_zones_by_room(room_id)


@router.get("/zones/rooms/{room_id}", response_model=List[ZoneResponse])
def list_room_zones_alias(
    room_id: str,
    db: Session = Depends(get_db),
) -> List[ZoneResponse]:
    return ZoneService(db).list_zones_by_room(room_id)


@router.post(
    "/rooms/{room_id}/zones",
    response_model=ZoneResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_room_zone(
    room_id: str,
    dto: ZoneCreateRequest,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> ZoneResponse:
    return ZoneService(db).create_zone(room_id, dto)


@router.post(
    "/zones",
    response_model=ZoneResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_zone_direct(
    dto: ZoneCreateRequest,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> ZoneResponse:
    if not dto.room_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="room_id (or roomId) is required when creating a zone via /zones.",
        )
    return ZoneService(db).create_zone(dto.room_id, dto)


@router.put("/zones/{zone_id}", response_model=ZoneResponse)
def update_zone_put(
    zone_id: str,
    dto: ZoneUpdateRequest,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> ZoneResponse:
    return ZoneService(db).update_zone(zone_id, dto)


@router.patch("/zones/{zone_id}", response_model=ZoneResponse)
def update_zone_patch(
    zone_id: str,
    dto: ZoneUpdateRequest,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> ZoneResponse:
    return ZoneService(db).update_zone(zone_id, dto)


@router.delete("/zones/{zone_id}")
def delete_zone(
    zone_id: str,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return ZoneService(db).delete_zone(zone_id)
