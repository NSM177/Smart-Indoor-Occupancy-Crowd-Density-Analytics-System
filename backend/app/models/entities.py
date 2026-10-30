"""
SQLAlchemy 2.0 ORM Entities (9 non-redundant tables):
1. User (`users`)
2. Room (`rooms`)
3. Zone (`zones`)
4. Device (`devices`)
5. OccupancyRecord (`occupancy_records`)
6. DensityRecord (`density_records`)
7. Alert (`alerts`)
8. DeviceStatusLog (`device_status_logs`)
9. SystemEvent (`system_events`)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Table 1: System users with RBAC roles (`ADMIN`, `OPERATOR`)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="OPERATOR", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Room(Base):
    """Table 2: Monitored indoor rooms with capacity & crowd density thresholds."""

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    max_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    warning_threshold_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    critical_density_per_sqm: Mapped[float] = mapped_column(Float, nullable=False, default=0.80)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    zones: Mapped[List["Zone"]] = relationship(
        "Zone", back_populates="room", cascade="all, delete-orphan"
    )
    devices: Mapped[List["Device"]] = relationship(
        "Device", back_populates="room", cascade="all, delete-orphan"
    )
    occupancy_records: Mapped[List["OccupancyRecord"]] = relationship(
        "OccupancyRecord", back_populates="room", cascade="all, delete-orphan"
    )
    density_records: Mapped[List["DensityRecord"]] = relationship(
        "DensityRecord", back_populates="room", cascade="all, delete-orphan"
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert", back_populates="room", cascade="all, delete-orphan"
    )


class Zone(Base):
    """Table 3: Polygon sub-zones inside a Room (Zone A, Zone B, Zone C...)."""

    __tablename__ = "zones"
    __table_args__ = (
        UniqueConstraint("room_id", "code", name="uq_zones_room_code"),
        Index("idx_zones_room_id", "room_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    room_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    polygon_coordinates: Mapped[List[Dict[str, float]]] = mapped_column(JSON, nullable=False)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    max_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_density: Mapped[float] = mapped_column(Float, nullable=False, default=0.50)
    critical_density: Mapped[float] = mapped_column(Float, nullable=False, default=0.80)
    color_hex: Mapped[str] = mapped_column(String(9), nullable=False, default="#3B82F6")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    room: Mapped["Room"] = relationship("Room", back_populates="zones")
    density_records: Mapped[List["DensityRecord"]] = relationship(
        "DensityRecord", back_populates="zone", cascade="all, delete-orphan"
    )
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="zone")


class Device(Base):
    """Table 4: Edge IoT nodes (Raspberry Pi) and Camera devices."""

    __tablename__ = "devices"
    __table_args__ = (
        Index("idx_devices_room_status", "room_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    room_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    device_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="RASPBERRY_PI_EDGE"
    )
    stream_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    resolution_width: Mapped[int] = mapped_column(Integer, nullable=False, default=1280)
    resolution_height: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    fps_target: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OFFLINE")
    led_state: Mapped[str] = mapped_column(String(16), nullable=False, default="GREEN")
    buzzer_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    gpio_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="SIMULATION")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    firmware_version: Mapped[str] = mapped_column(String(32), nullable=False, default="2.0.0")
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    room: Mapped["Room"] = relationship("Room", back_populates="devices")
    status_logs: Mapped[List["DeviceStatusLog"]] = relationship(
        "DeviceStatusLog", back_populates="device", cascade="all, delete-orphan"
    )


class OccupancyRecord(Base):
    """Table 5: Time-series room occupancy counts (IN, OUT, current count, room status)."""

    __tablename__ = "occupancy_records"
    __table_args__ = (
        Index("idx_occupancy_room_recorded", "room_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    out_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_density: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    capacity_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    room_status: Mapped[str] = mapped_column(String(24), nullable=False, default="NORMAL")
    inference_fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    room: Mapped["Room"] = relationship("Room", back_populates="occupancy_records")


class DensityRecord(Base):
    """Table 6: Time-series per-zone crowd density & spatial analytics."""

    __tablename__ = "density_records"
    __table_args__ = (
        Index("idx_density_room_zone_recorded", "room_id", "zone_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False
    )
    person_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    density_per_sqm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    capacity_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="NORMAL")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    room: Mapped["Room"] = relationship("Room", back_populates="density_records")
    zone: Mapped["Zone"] = relationship("Zone", back_populates="density_records")


class Alert(Base):
    """Table 7: Overcrowding & high-density alerts with acknowledge/resolve lifecycle."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_room_severity_status", "room_id", "severity", "is_resolved"),
        Index("idx_alerts_triggered_at", "triggered_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    room_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True
    )
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="WARNING")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    person_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    density_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    room: Mapped["Room"] = relationship("Room", back_populates="alerts")
    zone: Mapped[Optional["Zone"]] = relationship("Zone", back_populates="alerts")


class DeviceStatusLog(Base):
    """Table 8: Historical audit log of IoT edge telemetry, GPIO state, and commands."""

    __tablename__ = "device_status_logs"
    __table_args__ = (
        Index("idx_device_status_logs_device_logged", "device_id", "logged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    led_state: Mapped[str] = mapped_column(String(16), nullable=False)
    buzzer_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    person_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    density: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    device: Mapped["Device"] = relationship("Device", back_populates="status_logs")


class SystemEvent(Base):
    """Table 9: System audit & error log (MQTT malformed payloads, reconnects, auth events)."""

    __tablename__ = "system_events"
    __table_args__ = (
        Index("idx_system_events_source_created", "source", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="INFO")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="BACKEND")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
