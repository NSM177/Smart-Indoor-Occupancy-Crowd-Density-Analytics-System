"""Module 2 Router: Room Management (`/api/v1/rooms`)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import get_optional_user, require_admin
from app.database.session import get_db
from app.models.entities import User
from app.schemas.room import (
    RoomCreateRequest,
    RoomResponse,
    RoomUpdateRequest,
)
from app.services.business_services import RoomService

router = APIRouter(prefix="/rooms", tags=["Room Management"])


@router.get("", response_model=List[RoomResponse])
def list_rooms(db: Session = Depends(get_db)) -> List[RoomResponse]:
    return RoomService(db).list_rooms()


@router.post(
    "",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_room(
    dto: RoomCreateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RoomResponse:
    return RoomService(db).create_room(dto)


@router.get("/{room_id}", response_model=RoomResponse)
def get_room(
    room_id: str,
    db: Session = Depends(get_db),
) -> RoomResponse:
    return RoomService(db).get_room(room_id)


@router.put("/{room_id}", response_model=RoomResponse)
def update_room_put(
    room_id: str,
    dto: RoomUpdateRequest,
    _user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> RoomResponse:
    return RoomService(db).update_room(room_id, dto)


@router.patch("/{room_id}", response_model=RoomResponse)
def update_room_patch(
    room_id: str,
    dto: RoomUpdateRequest,
    _user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> RoomResponse:
    return RoomService(db).update_room(room_id, dto)


@router.delete("/{room_id}")
def delete_room(
    room_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return RoomService(db).delete_room(room_id)
