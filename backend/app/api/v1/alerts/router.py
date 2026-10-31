"""
Module 6 Router: Alert Management (`/api/v1/alerts`).
Endpoints:
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/{alert_id}`
- `PATCH /api/v1/alerts/{alert_id}/acknowledge`
- `PATCH /api/v1/alerts/{alert_id}/resolve`
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_operator_or_admin
from app.database.session import get_db
from app.models.entities import User
from app.schemas.alert import AlertResponse
from app.services.business_services import AlertService

router = APIRouter(prefix="/alerts", tags=["Alert Management"])


@router.get("", response_model=List[AlertResponse])
def list_alerts(
    roomId: Optional[str] = Query(default=None),
    room_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    onlyUnresolved: bool = Query(default=False),
    only_unresolved: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[AlertResponse]:
    target_room = room_id or roomId
    unresolved_flag = only_unresolved or onlyUnresolved
    return AlertService(db).list_alerts(
        room_identifier=target_room,
        severity=severity,
        only_unresolved=unresolved_flag,
        limit=limit,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db),
) -> AlertResponse:
    return AlertService(db).get_alert(alert_id)


@router.patch("/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> AlertResponse:
    user_id = current_user.id
    return AlertService(db).acknowledge_alert(alert_id, user_id=user_id)


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: str,
    current_user: User = Depends(require_operator_or_admin),
    db: Session = Depends(get_db),
) -> AlertResponse:
    user_id = current_user.id
    return AlertService(db).resolve_alert(alert_id, user_id=user_id)
