"""
Idempotent database seeder for initial users, room, polygon zones, and IoT/camera devices.
All parameters are driven by environment settings (`BackendSettings`) without hardcoded business rules.
"""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.entities import Device, Room, User, Zone

logger = logging.getLogger("backend.seed")


def seed_initial_data(db: Session) -> None:
    """Seed initial Admin/Operator accounts, Room, Polygon Zones, and Edge Devices if missing."""
    # 1. Seed Users (Admin & Operator)
    admin_user = (
        db.query(User)
        .filter(User.username == settings.DEFAULT_ADMIN_USERNAME)
        .first()
    )
    if not admin_user:
        db.add(
            User(
                username=settings.DEFAULT_ADMIN_USERNAME,
                email=f"{settings.DEFAULT_ADMIN_USERNAME}@occupancy.local",
                password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                full_name="System Administrator",
                role="ADMIN",
                is_active=True,
            )
        )

    operator_user = (
        db.query(User)
        .filter(User.username == settings.DEFAULT_OPERATOR_USERNAME)
        .first()
    )
    if not operator_user:
        db.add(
            User(
                username=settings.DEFAULT_OPERATOR_USERNAME,
                email=f"{settings.DEFAULT_OPERATOR_USERNAME}@occupancy.local",
                password_hash=hash_password(settings.DEFAULT_OPERATOR_PASSWORD),
                full_name="Control Room Operator",
                role="OPERATOR",
                is_active=True,
            )
        )

    db.flush()

    # 2. Seed Default Room (`room1`)
    room = (
        db.query(Room)
        .filter(Room.code == settings.INITIAL_ROOM_CODE)
        .first()
    )
    if not room:
        room = Room(
            code=settings.INITIAL_ROOM_CODE,
            name=settings.INITIAL_ROOM_NAME,
            description="Primary indoor space monitored by AI Computer Vision & Raspberry Pi IoT node.",
            area_sqm=settings.INITIAL_ROOM_AREA_SQM,
            max_capacity=settings.INITIAL_ROOM_MAX_CAPACITY,
            warning_threshold_ratio=0.75,
            critical_density_per_sqm=0.80,
            is_active=True,
        )
        db.add(room)
        db.flush()

    # 3. Seed Default Zones (matching ai-service/config/zones.json)
    existing_zones = db.query(Zone).filter(Zone.room_id == room.id).count()
    if existing_zones == 0:
        default_zones = [
            Zone(
                room_id=room.id,
                name="Zone A - Entrance & Reception",
                code="ZONE_A",
                polygon_coordinates=[
                    {"x": 0.02, "y": 0.05},
                    {"x": 0.35, "y": 0.05},
                    {"x": 0.35, "y": 0.95},
                    {"x": 0.02, "y": 0.95},
                ],
                area_sqm=round(room.area_sqm * 0.30, 2),
                max_capacity=max(5, int(room.max_capacity * 0.30)),
                warning_density=0.50,
                critical_density=0.80,
                color_hex="#3B82F6",
            ),
            Zone(
                room_id=room.id,
                name="Zone B - Central Main Floor",
                code="ZONE_B",
                polygon_coordinates=[
                    {"x": 0.36, "y": 0.05},
                    {"x": 0.68, "y": 0.05},
                    {"x": 0.68, "y": 0.95},
                    {"x": 0.36, "y": 0.95},
                ],
                area_sqm=round(room.area_sqm * 0.45, 2),
                max_capacity=max(5, int(room.max_capacity * 0.45)),
                warning_density=0.50,
                critical_density=0.80,
                color_hex="#10B981",
            ),
            Zone(
                room_id=room.id,
                name="Zone C - Exit & Corridor",
                code="ZONE_C",
                polygon_coordinates=[
                    {"x": 0.69, "y": 0.05},
                    {"x": 0.98, "y": 0.05},
                    {"x": 0.98, "y": 0.95},
                    {"x": 0.69, "y": 0.95},
                ],
                area_sqm=round(room.area_sqm * 0.25, 2),
                max_capacity=max(5, int(room.max_capacity * 0.25)),
                warning_density=0.50,
                critical_density=0.80,
                color_hex="#F59E0B",
            ),
        ]
        db.add_all(default_zones)
        db.flush()

    # 4. Seed Default Devices (Raspberry Pi Edge + Camera)
    rpi_device = (
        db.query(Device)
        .filter(Device.device_code == settings.IOT_DEVICE_ID)
        .first()
    )
    if not rpi_device:
        db.add(
            Device(
                room_id=room.id,
                device_code=settings.IOT_DEVICE_ID,
                name=f"Raspberry Pi 4/5 Edge Controller ({settings.IOT_DEVICE_ID})",
                device_type="RASPBERRY_PI_EDGE",
                stream_url=settings.INITIAL_CAMERA_STREAM_URL,
                resolution_width=1280,
                resolution_height=720,
                fps_target=15,
                status="ONLINE",
                led_state="GREEN",
                buzzer_active=False,
                auto_mode=True,
                gpio_mode="SIMULATION",
                firmware_version="2.0.0",
            )
        )

    db.commit()
    logger.info("Initial seed data verified for room '%s'.", room.code)
