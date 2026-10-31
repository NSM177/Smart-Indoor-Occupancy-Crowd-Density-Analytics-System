"""
Business Service Layer implementing all 8 domain modules:
1. AuthService (Module 1)
2. RoomService (Module 2)
3. ZoneService (Module 3)
4. OccupancyService (Module 4)
5. DensityService (Module 5)
6. AlertService (Module 6)
7. DeviceService (Module 7)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DomainError, EntityNotFoundError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    hash_password,
    revoke_token,
    verify_password,
)
from app.models.entities import (
    Alert,
    Device,
    DeviceStatusLog,
    Room,
    User,
    Zone,
)
from app.mqtt.worker import classify_severity, mqtt_worker
from app.repositories.crud_repositories import (
    AlertRepository,
    DensityRepository,
    DeviceRepository,
    OccupancyRepository,
    RoomRepository,
    UserRepository,
    ZoneRepository,
)
from app.schemas.alert import AlertResponse
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from app.schemas.density import (
    DensityRecordResponse,
    RoomDensityCurrentResponse,
    ZoneDensitySnapshot,
)
from app.schemas.device import DeviceCommandRequest, DeviceResponse
from app.schemas.occupancy import (
    OccupancyCurrentResponse,
    OccupancyRecordResponse,
)
from app.schemas.room import RoomCreateRequest, RoomResponse, RoomUpdateRequest
from app.schemas.zone import ZoneCreateRequest, ZoneResponse, ZoneUpdateRequest


class AuthService:
    """Module 1: Authentication, JWT issuance/refresh/revocation, and user management."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = UserRepository(db)

    def login(self, dto: LoginRequest) -> TokenResponse:
        user = self.repo.get_by_username(dto.username)
        if not user or not verify_password(dto.password, user.password_hash):
            raise DomainError(
                "Invalid username or password.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            raise DomainError(
                "User account is disabled.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        access_token = create_access_token(user.id, user.username, user.role)
        refresh_token = create_refresh_token(user.id, user.username, user.role)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        payload = decode_jwt_token(refresh_token, expected_type="refresh")
        user_id = str(payload.get("sub"))
        user = self.repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise DomainError(
                "User not found or inactive.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        revoke_token(refresh_token)
        new_access = create_access_token(user.id, user.username, user.role)
        new_refresh = create_refresh_token(user.id, user.username, user.role)
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    def logout(
        self, access_token: Optional[str], refresh_token: Optional[str] = None
    ) -> Dict[str, Any]:
        if access_token:
            revoke_token(access_token)
        if refresh_token:
            revoke_token(refresh_token)
        return {"status": "logged_out", "timestamp": datetime.now(timezone.utc).isoformat()}

    def create_user(self, dto: UserCreateRequest) -> UserResponse:
        if self.repo.get_by_username(dto.username):
            raise DomainError(
                f"Username '{dto.username}' is already taken.",
                status_code=status.HTTP_409_CONFLICT,
            )
        if self.repo.get_by_email(dto.email):
            raise DomainError(
                f"Email '{dto.email}' is already registered.",
                status_code=status.HTTP_409_CONFLICT,
            )
        user = User(
            username=dto.username,
            email=dto.email,
            password_hash=hash_password(dto.password),
            full_name=dto.full_name,
            role=dto.role,
            is_active=True,
        )
        saved = self.repo.create(user)
        return UserResponse.model_validate(saved)

    def list_users(self) -> List[UserResponse]:
        return [UserResponse.model_validate(u) for u in self.repo.list_users()]


class RoomService:
    """Module 2: Room CRUD, capacity/threshold management & MQTT sync."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = RoomRepository(db)
        self.zone_repo = ZoneRepository(db)

    def list_rooms(self) -> List[RoomResponse]:
        return [RoomResponse.from_orm_room(r) for r in self.repo.list_all()]

    def get_room_entity(self, identifier: str) -> Room:
        room = self.repo.get_by_id_or_code(identifier)
        if not room:
            raise EntityNotFoundError("Room", identifier)
        return room

    def get_room(self, identifier: str) -> RoomResponse:
        return RoomResponse.from_orm_room(self.get_room_entity(identifier))

    def create_room(self, dto: RoomCreateRequest) -> RoomResponse:
        code = (
            dto.code.strip()
            if dto.code
            else f"room_{uuid.uuid4().hex[:6]}"
        )
        if self.repo.get_by_id_or_code(code):
            raise DomainError(
                f"Room with code '{code}' already exists.",
                status_code=status.HTTP_409_CONFLICT,
            )
        room = Room(
            code=code,
            name=dto.name,
            description=dto.description,
            area_sqm=dto.area_sqm,
            max_capacity=dto.max_capacity,
            warning_threshold_ratio=dto.warning_threshold_ratio,
            critical_density_per_sqm=dto.critical_density_per_sqm,
            is_active=dto.is_active,
        )
        saved = self.repo.create(room)
        mqtt_worker.publish_room_config(saved, [])
        return RoomResponse.from_orm_room(saved)

    def update_room(self, identifier: str, dto: RoomUpdateRequest) -> RoomResponse:
        room = self.get_room_entity(identifier)
        if dto.code is not None and dto.code != room.code:
            existing = self.repo.get_by_id_or_code(dto.code)
            if existing and existing.id != room.id:
                raise DomainError(
                    f"Room code '{dto.code}' is already in use.",
                    status_code=status.HTTP_409_CONFLICT,
                )
            room.code = dto.code
        if dto.name is not None:
            room.name = dto.name
        if dto.description is not None:
            room.description = dto.description
        if dto.area_sqm is not None:
            room.area_sqm = dto.area_sqm
        if dto.max_capacity is not None:
            room.max_capacity = dto.max_capacity
        if dto.warning_threshold_ratio is not None:
            room.warning_threshold_ratio = dto.warning_threshold_ratio
        if dto.critical_density_per_sqm is not None:
            room.critical_density_per_sqm = dto.critical_density_per_sqm
        if dto.is_active is not None:
            room.is_active = dto.is_active

        saved = self.repo.update(room)
        zones = self.zone_repo.list_by_room(saved.id)
        mqtt_worker.publish_room_config(saved, zones)
        return RoomResponse.from_orm_room(saved)

    def delete_room(self, identifier: str) -> Dict[str, Any]:
        room = self.get_room_entity(identifier)
        room_id = room.id
        self.repo.delete(room)
        return {"deleted": True, "id": room_id}


class ZoneService:
    """Module 3: Polygon Zone CRUD, coordinate & area calibration, MQTT config sync."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.room_service = RoomService(db)
        self.repo = ZoneRepository(db)

    def list_zones_by_room(self, room_identifier: str) -> List[ZoneResponse]:
        room = self.room_service.get_room_entity(room_identifier)
        zones = self.repo.list_by_room(room.id)
        return [ZoneResponse.from_orm_zone(z) for z in zones]

    def create_zone(
        self, room_identifier: str, dto: ZoneCreateRequest
    ) -> ZoneResponse:
        room = self.room_service.get_room_entity(room_identifier)
        if self.repo.get_by_room_and_code(room.id, dto.code):
            raise DomainError(
                f"Zone with code '{dto.code}' already exists in room '{room.code}'.",
                status_code=status.HTTP_409_CONFLICT,
            )
        coords = [{"x": float(p.x), "y": float(p.y)} for p in dto.polygon_coordinates]
        zone = Zone(
            room_id=room.id,
            name=dto.name,
            code=dto.code,
            polygon_coordinates=coords,
            area_sqm=dto.area_sqm,
            max_capacity=dto.max_capacity,
            warning_density=dto.warning_density,
            critical_density=dto.critical_density,
            color_hex=dto.color_hex,
        )
        saved = self.repo.create(zone)
        all_zones = self.repo.list_by_room(room.id)
        mqtt_worker.publish_room_config(room, all_zones)
        return ZoneResponse.from_orm_zone(saved)

    def update_zone(self, zone_id: str, dto: ZoneUpdateRequest) -> ZoneResponse:
        zone = self.repo.get_by_id(zone_id)
        if not zone:
            raise EntityNotFoundError("Zone", zone_id)

        if dto.name is not None:
            zone.name = dto.name
        if dto.code is not None and dto.code != zone.code:
            dup = self.repo.get_by_room_and_code(zone.room_id, dto.code)
            if dup and dup.id != zone.id:
                raise DomainError(
                    f"Zone code '{dto.code}' already exists in this room.",
                    status_code=status.HTTP_409_CONFLICT,
                )
            zone.code = dto.code
        if dto.polygon_coordinates is not None:
            zone.polygon_coordinates = [
                {"x": float(p.x), "y": float(p.y)}
                for p in dto.polygon_coordinates
            ]
        if dto.area_sqm is not None:
            zone.area_sqm = dto.area_sqm
        if dto.max_capacity is not None:
            zone.max_capacity = dto.max_capacity
        if dto.warning_density is not None:
            zone.warning_density = dto.warning_density
        if dto.critical_density is not None:
            zone.critical_density = dto.critical_density
        if dto.color_hex is not None:
            zone.color_hex = dto.color_hex

        saved = self.repo.update(zone)
        room = self.room_service.get_room_entity(saved.room_id)
        all_zones = self.repo.list_by_room(room.id)
        mqtt_worker.publish_room_config(room, all_zones)
        return ZoneResponse.from_orm_zone(saved)

    def delete_zone(self, zone_id: str) -> Dict[str, Any]:
        zone = self.repo.get_by_id(zone_id)
        if not zone:
            raise EntityNotFoundError("Zone", zone_id)
        room_id = zone.room_id
        self.repo.delete(zone)
        room = self.room_service.get_room_entity(room_id)
        all_zones = self.repo.list_by_room(room.id)
        mqtt_worker.publish_room_config(room, all_zones)
        return {"deleted": True, "id": zone_id}


class OccupancyService:
    """Module 4: Current & Historical Room Occupancy (IN, OUT, Current Count, Status)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.room_service = RoomService(db)
        self.repo = OccupancyRepository(db)

    def get_current_occupancy(
        self, room_identifier: str
    ) -> OccupancyCurrentResponse:
        room = self.room_service.get_room_entity(room_identifier)
        live = mqtt_worker.get_live_room_state(room.id) or mqtt_worker.get_live_room_state(
            room.code
        )
        # DB fallback is only needed when no live MQTT state exists
        latest = None if live else self.repo.get_latest_by_room(room.id)

        if live:
            cur_count = int(live.get("current_count", 0))
            in_cnt = int(live.get("in_count", 0))
            out_cnt = int(live.get("out_count", 0))
            fps = live.get("inference_fps")
            updated_at = datetime.now(timezone.utc)
        elif latest:
            cur_count = latest.total_count
            in_cnt = latest.in_count
            out_cnt = latest.out_count
            fps = latest.inference_fps
            updated_at = latest.recorded_at
        else:
            cur_count = 0
            in_cnt = 0
            out_cnt = 0
            fps = None
            updated_at = datetime.now(timezone.utc)

        overall_density = round(cur_count / max(1.0, room.area_sqm), 4)
        cap_ratio = round(cur_count / max(1, room.max_capacity), 4)
        room_status = classify_severity(
            count=cur_count,
            max_capacity=room.max_capacity,
            density_per_sqm=overall_density,
            warning_ratio=room.warning_threshold_ratio,
            critical_density=room.critical_density_per_sqm,
        )

        return OccupancyCurrentResponse(
            room_id=room.id,
            room_code=room.code,
            room_name=room.name,
            current_count=cur_count,
            in_count=in_cnt,
            out_count=out_cnt,
            max_capacity=room.max_capacity,
            capacity_ratio=cap_ratio,
            overall_density=overall_density,
            room_status=room_status,
            inference_fps=fps,
            updated_at=updated_at,
            roomId=room.id,
            totalCount=cur_count,
            inCount=in_cnt,
            outCount=out_cnt,
            maxCapacity=room.max_capacity,
            capacityRatio=cap_ratio,
            overallDensity=overall_density,
            roomStatus=room_status,
        )

    def get_occupancy_history(
        self,
        room_identifier: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 200,
    ) -> List[OccupancyRecordResponse]:
        room = self.room_service.get_room_entity(room_identifier)
        records = self.repo.list_history(
            room_id=room.id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        return [OccupancyRecordResponse.from_orm_record(r) for r in records]


class DensityService:
    """Module 5: Per-zone Crowd Density, Busiest Zone identification & Capacity Utilization %."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.room_service = RoomService(db)
        self.zone_repo = ZoneRepository(db)
        self.occ_repo = OccupancyRepository(db)
        self.den_repo = DensityRepository(db)

    def get_current_density(
        self, room_identifier: str
    ) -> RoomDensityCurrentResponse:
        room = self.room_service.get_room_entity(room_identifier)
        # Zones are already eager-loaded with the room; avoid a second query
        zones = sorted(room.zones, key=lambda z: z.code)
        live = mqtt_worker.get_live_room_state(room.id)

        live_zones_by_code: Dict[str, Dict[str, Any]] = {}
        if live and isinstance(live.get("zones"), list):
            for lz in live["zones"]:
                code = lz.get("zoneCode") or lz.get("code")
                if code:
                    live_zones_by_code[str(code)] = lz

        # Query persisted per-zone history only for zones missing from live state
        latest_zone_map: Dict[str, Any] = {}
        if any(z.code not in live_zones_by_code for z in zones):
            latest_zone_map = self.den_repo.get_latest_per_zone(room.id)

        zone_snapshots: List[ZoneDensitySnapshot] = []
        for z in zones:
            if z.code in live_zones_by_code:
                p_count = int(live_zones_by_code[z.code].get("count", 0))
            elif z.id in latest_zone_map:
                p_count = latest_zone_map[z.id].person_count
            else:
                p_count = 0

            den_sqm = round(p_count / max(0.5, z.area_sqm), 4)
            cap_ratio = round(p_count / max(1, z.max_capacity), 4)
            util_pct = round(cap_ratio * 100.0, 2)
            sev = classify_severity(
                count=p_count,
                max_capacity=z.max_capacity,
                density_per_sqm=den_sqm,
                warning_ratio=0.75,
                critical_density=z.critical_density,
            )
            zone_snapshots.append(
                ZoneDensitySnapshot(
                    zone_id=z.id,
                    zone_code=z.code,
                    zone_name=z.name,
                    person_count=p_count,
                    area_sqm=z.area_sqm,
                    max_capacity=z.max_capacity,
                    density_per_sqm=den_sqm,
                    capacity_ratio=cap_ratio,
                    utilization_pct=util_pct,
                    severity=sev,
                )
            )

        latest_occ = None
        if not (live and "current_count" in live):
            latest_occ = self.occ_repo.get_latest_by_room(room.id)

        if live and "current_count" in live:
            total_count = int(live["current_count"])
        elif latest_occ:
            total_count = latest_occ.total_count
        else:
            total_count = sum(zs.person_count for zs in zone_snapshots)

        overall_density = round(total_count / max(1.0, room.area_sqm), 4)
        cap_util_pct = round(
            (total_count / max(1, room.max_capacity)) * 100.0, 2
        )
        room_status = classify_severity(
            count=total_count,
            max_capacity=room.max_capacity,
            density_per_sqm=overall_density,
            warning_ratio=room.warning_threshold_ratio,
            critical_density=room.critical_density_per_sqm,
        )

        busiest: Optional[ZoneDensitySnapshot] = None
        if zone_snapshots:
            busiest = max(
                zone_snapshots,
                key=lambda item: (item.density_per_sqm, item.person_count),
            )

        return RoomDensityCurrentResponse(
            room_id=room.id,
            room_code=room.code,
            room_name=room.name,
            total_count=total_count,
            area_sqm=room.area_sqm,
            max_capacity=room.max_capacity,
            overall_density_per_sqm=overall_density,
            capacity_utilization_pct=cap_util_pct,
            room_status=room_status,
            busiest_zone=busiest,
            zones=zone_snapshots,
            updated_at=datetime.now(timezone.utc),
        )

    def get_density_history(
        self,
        room_identifier: str,
        zone_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 300,
    ) -> List[DensityRecordResponse]:
        room = self.room_service.get_room_entity(room_identifier)
        zones_map = {z.id: z for z in self.zone_repo.list_by_room(room.id)}
        records = self.den_repo.list_history(
            room_id=room.id,
            zone_id=zone_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        out: List[DensityRecordResponse] = []
        for r in records:
            z = zones_map.get(r.zone_id)
            out.append(
                DensityRecordResponse(
                    id=r.id,
                    room_id=r.room_id,
                    zone_id=r.zone_id,
                    zone_code=z.code if z else None,
                    zone_name=z.name if z else None,
                    person_count=r.person_count,
                    density_per_sqm=r.density_per_sqm,
                    capacity_ratio=r.capacity_ratio,
                    severity=r.severity,
                    recorded_at=r.recorded_at,
                )
            )
        return out


class AlertService:
    """Module 6: Alert querying, acknowledgement, and resolution."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AlertRepository(db)
        self.room_repo = RoomRepository(db)

    def list_alerts(
        self,
        room_identifier: Optional[str] = None,
        severity: Optional[str] = None,
        only_unresolved: bool = False,
        limit: int = 100,
    ) -> List[AlertResponse]:
        resolved_room_id: Optional[str] = None
        if room_identifier:
            room = self.room_repo.get_by_id_or_code(room_identifier)
            resolved_room_id = room.id if room else room_identifier

        alerts = self.repo.list_alerts(
            room_id=resolved_room_id,
            severity=severity,
            only_unresolved=only_unresolved,
            limit=limit,
        )
        return [AlertResponse.from_orm_alert(a) for a in alerts]

    def get_alert(self, alert_id: str) -> AlertResponse:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise EntityNotFoundError("Alert", alert_id)
        return AlertResponse.from_orm_alert(alert)

    def acknowledge_alert(
        self, alert_id: str, user_id: Optional[str] = None
    ) -> AlertResponse:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise EntityNotFoundError("Alert", alert_id)
        alert.is_acknowledged = True
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(timezone.utc)
        saved = self.repo.update(alert)
        return AlertResponse.from_orm_alert(saved)

    def resolve_alert(
        self, alert_id: str, user_id: Optional[str] = None
    ) -> AlertResponse:
        alert = self.repo.get_by_id(alert_id)
        if not alert:
            raise EntityNotFoundError("Alert", alert_id)
        now = datetime.now(timezone.utc)
        alert.is_acknowledged = True
        if user_id and not alert.acknowledged_by:
            alert.acknowledged_by = user_id
        if not alert.acknowledged_at:
            alert.acknowledged_at = now
        alert.is_resolved = True
        alert.resolved_at = now
        saved = self.repo.update(alert)
        return AlertResponse.from_orm_alert(saved)


class DeviceService:
    """Module 7: Raspberry Pi & Camera Device Monitoring, Heartbeat Offline Detection & Commands."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DeviceRepository(db)
        self.room_repo = RoomRepository(db)

    def _evaluate_online(self, device: Device) -> bool:
        if device.last_heartbeat is None:
            return device.status == "ONLINE"
        hb = device.last_heartbeat
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - hb).total_seconds()
        if elapsed > settings.DEVICE_OFFLINE_TIMEOUT_SEC:
            if device.status != "OFFLINE":
                device.status = "OFFLINE"
                self.repo.update(device)
            return False
        return device.status == "ONLINE"

    def list_devices(
        self, room_identifier: Optional[str] = None
    ) -> List[DeviceResponse]:
        room_id: Optional[str] = None
        if room_identifier:
            room = self.room_repo.get_by_id_or_code(room_identifier)
            room_id = room.id if room else room_identifier
        devices = self.repo.list_all(room_id=room_id)
        return [
            DeviceResponse.from_orm_device(d, is_online=self._evaluate_online(d))
            for d in devices
        ]

    def get_device_status(self, identifier: str) -> DeviceResponse:
        device = self.repo.get_by_id_or_code(identifier)
        if not device:
            raise EntityNotFoundError("Device", identifier)
        online = self._evaluate_online(device)
        return DeviceResponse.from_orm_device(device, is_online=online)

    def send_command(
        self, identifier: str, cmd: DeviceCommandRequest
    ) -> Dict[str, Any]:
        device = self.repo.get_by_id_or_code(identifier)
        if not device:
            raise EntityNotFoundError("Device", identifier)
        room = self.room_repo.get_by_id_or_code(device.room_id)
        room_code = room.code if room else settings.INITIAL_ROOM_CODE

        if cmd.led_state is not None:
            device.led_state = cmd.led_state
        if cmd.buzzer_active is not None:
            device.buzzer_active = cmd.buzzer_active
        if cmd.auto_mode is not None:
            device.auto_mode = cmd.auto_mode

        saved = self.repo.update(device)
        mqtt_worker.invalidate_actuation_cache(saved.room_id)
        command_payload = {
            "ledState": saved.led_state,
            "buzzerActive": saved.buzzer_active,
            "autoMode": saved.auto_mode,
            "resetCounters": bool(cmd.reset_counters),
        }
        self.repo.add_status_log(
            DeviceStatusLog(
                device_id=saved.id,
                status=saved.status,
                led_state=saved.led_state,
                buzzer_active=saved.buzzer_active,
                auto_mode=saved.auto_mode,
                person_count=0,
                density=0.0,
                raw_payload={"manual_command": command_payload},
            )
        )
        published = mqtt_worker.publish_device_command(
            room_code=room_code,
            device_code=saved.device_code,
            command=command_payload,
        )
        return {
            "dispatched": True,
            "mqtt_published": published,
            "device": DeviceResponse.from_orm_device(saved),
            "command": command_payload,
        }
