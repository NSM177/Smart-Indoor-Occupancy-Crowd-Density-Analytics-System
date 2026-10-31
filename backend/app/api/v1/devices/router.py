"""
Module 7 Router: IoT Edge & Camera Device Management.
Endpoints:
- `GET /api/v1/devices` (and `/api/v1/iot/devices`)
- `GET /api/v1/devices/{device_id}/status`
- `POST /api/v1/devices/{device_id}/commands` (and `/api/v1/iot/devices/{device_id}/command`)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_operator_or_admin
from app.database.session import get_db
from app.models.entities import User
from app.schemas.device import DeviceCommandRequest, DeviceResponse
from app.services.business_services import DeviceService

router = APIRouter(tags=["Device Management"])


@router.get("/devices", response_model=List[DeviceResponse])
def list_devices(
    room_id: Optional[str] = Query(default=None),
    roomId: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[DeviceResponse]:
    return DeviceService(db).list_devices(room_identifier=room_id or roomId)


@router.get("/iot/devices", response_model=List[DeviceResponse])
def list_devices_iot_alias(
    roomId: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[DeviceResponse]:
    return DeviceService(db).list_devices(room_identifier=roomId)


@router.get("/devices/{device_id}/status", response_model=DeviceResponse)
def get_device_status(
    device_id: str,
    db: Session = Depends(get_db),
) -> DeviceResponse:
    return DeviceService(db).get_device_status(device_id)


@router.post("/devices/{device_id}/commands")
def send_device_command(
    device_id: str,
    cmd: DeviceCommandRequest,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return DeviceService(db).send_command(device_id, cmd)


@router.post("/iot/devices/{device_id}/command")
def send_device_command_iot_alias(
    device_id: str,
    cmd: DeviceCommandRequest,
    _user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return DeviceService(db).send_command(device_id, cmd)
