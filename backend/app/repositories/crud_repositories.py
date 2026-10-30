"""
Typed Repositories encapsulating SQLAlchemy 2.0 queries and transactions.
Each repository has a single responsibility over its entity domain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    Alert,
    DensityRecord,
    Device,
    DeviceStatusLog,
    OccupancyRecord,
    Room,
    SystemEvent,
    User,
    Zone,
)


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def list_users(self) -> List[User]:
        return self.db.query(User).order_by(User.created_at.asc()).all()

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user


class RoomRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self) -> List[Room]:
        return (
            self.db.query(Room)
            .options(joinedload(Room.zones))
            .order_by(Room.created_at.asc())
            .all()
        )

    def get_by_id_or_code(self, identifier: str) -> Optional[Room]:
        return (
            self.db.query(Room)
            .options(joinedload(Room.zones))
            .filter(or_(Room.id == identifier, Room.code == identifier))
            .first()
        )

    def create(self, room: Room) -> Room:
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return room

    def update(self, room: Room) -> Room:
        self.db.commit()
        self.db.refresh(room)
        return room

    def delete(self, room: Room) -> None:
        self.db.delete(room)
        self.db.commit()


class ZoneRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_room(self, room_id: str) -> List[Zone]:
        return (
            self.db.query(Zone)
            .filter(Zone.room_id == room_id)
            .order_by(Zone.code.asc())
            .all()
        )

    def get_by_id(self, zone_id: str) -> Optional[Zone]:
        return self.db.query(Zone).filter(Zone.id == zone_id).first()

    def get_by_room_and_code(self, room_id: str, code: str) -> Optional[Zone]:
        return (
            self.db.query(Zone)
            .filter(Zone.room_id == room_id, Zone.code == code)
            .first()
        )

    def create(self, zone: Zone) -> Zone:
        self.db.add(zone)
        self.db.commit()
        self.db.refresh(zone)
        return zone

    def update(self, zone: Zone) -> Zone:
        self.db.commit()
        self.db.refresh(zone)
        return zone

    def delete(self, zone: Zone) -> None:
        self.db.delete(zone)
        self.db.commit()


class OccupancyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest_by_room(self, room_id: str) -> Optional[OccupancyRecord]:
        return (
            self.db.query(OccupancyRecord)
            .filter(OccupancyRecord.room_id == room_id)
            .order_by(desc(OccupancyRecord.recorded_at), desc(OccupancyRecord.id))
            .first()
        )

    def list_history(
        self,
        room_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200,
    ) -> List[OccupancyRecord]:
        query = self.db.query(OccupancyRecord).filter(
            OccupancyRecord.room_id == room_id
        )
        if start_time:
            query = query.filter(OccupancyRecord.recorded_at >= start_time)
        if end_time:
            query = query.filter(OccupancyRecord.recorded_at <= end_time)
        return (
            query.order_by(desc(OccupancyRecord.recorded_at), desc(OccupancyRecord.id))
            .limit(max(1, min(limit, 2000)))
            .all()
        )

    def create(self, record: OccupancyRecord) -> OccupancyRecord:
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record


class DensityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest_per_zone(self, room_id: str) -> Dict[str, DensityRecord]:
        zones = self.db.query(Zone).filter(Zone.room_id == room_id).all()
        latest_map: Dict[str, DensityRecord] = {}
        for z in zones:
            rec = (
                self.db.query(DensityRecord)
                .filter(
                    DensityRecord.room_id == room_id,
                    DensityRecord.zone_id == z.id,
                )
                .order_by(desc(DensityRecord.recorded_at), desc(DensityRecord.id))
                .first()
            )
            if rec:
                latest_map[z.id] = rec
        return latest_map

    def list_history(
        self,
        room_id: str,
        zone_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 300,
    ) -> List[DensityRecord]:
        query = self.db.query(DensityRecord).filter(
            DensityRecord.room_id == room_id
        )
        if zone_id:
            query = query.filter(DensityRecord.zone_id == zone_id)
        if start_time:
            query = query.filter(DensityRecord.recorded_at >= start_time)
        if end_time:
            query = query.filter(DensityRecord.recorded_at <= end_time)
        return (
            query.order_by(desc(DensityRecord.recorded_at), desc(DensityRecord.id))
            .limit(max(1, min(limit, 2000)))
            .all()
        )


class AlertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_alerts(
        self,
        room_id: Optional[str] = None,
        severity: Optional[str] = None,
        only_unresolved: bool = False,
        limit: int = 100,
    ) -> List[Alert]:
        query = self.db.query(Alert)
        if room_id:
            query = query.filter(Alert.room_id == room_id)
        if severity:
            query = query.filter(Alert.severity == severity.upper())
        if only_unresolved:
            query = query.filter(Alert.is_resolved.is_(False))
        return (
            query.order_by(desc(Alert.triggered_at))
            .limit(max(1, min(limit, 500)))
            .all()
        )

    def get_by_id(self, alert_id: str) -> Optional[Alert]:
        return self.db.query(Alert).filter(Alert.id == alert_id).first()

    def create(self, alert: Alert) -> Alert:
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def update(self, alert: Alert) -> Alert:
        self.db.commit()
        self.db.refresh(alert)
        return alert


class DeviceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(self, room_id: Optional[str] = None) -> List[Device]:
        query = self.db.query(Device)
        if room_id:
            query = query.filter(Device.room_id == room_id)
        return query.order_by(Device.device_code.asc()).all()

    def get_by_id_or_code(self, identifier: str) -> Optional[Device]:
        return (
            self.db.query(Device)
            .filter(or_(Device.id == identifier, Device.device_code == identifier))
            .first()
        )

    def update(self, device: Device) -> Device:
        self.db.commit()
        self.db.refresh(device)
        return device

    def add_status_log(self, log_entry: DeviceStatusLog) -> DeviceStatusLog:
        self.db.add(log_entry)
        self.db.commit()
        return log_entry


class SystemEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log_event(
        self,
        event_type: str,
        message: str,
        severity: str = "INFO",
        source: str = "BACKEND",
        details: Optional[Dict[str, Any]] = None,
    ) -> SystemEvent:
        event = SystemEvent(
            event_type=event_type,
            severity=severity,
            source=source,
            message=message,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
