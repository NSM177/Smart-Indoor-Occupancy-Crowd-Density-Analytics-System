"""
Asynchronous MQTT Broker Integration & Background Worker.
Key architectural guarantees:
- 100% topic & payload compatibility with `ai-service` and `iot-service`
- Non-blocking Paho-MQTT callback pushing messages to an `asyncio.Queue`
- Automatic reconnection with backoff
- Strict Pydantic v2 validation; invalid payloads are logged to `system_events`
- Retained (`msg.retain == True`) vs Realtime (`msg.retain == False`) distinction
- Duplicate burst filtering via content hash window
- Automatic Alert evaluation & IoT LED/Buzzer actuation
- WebSocket broadcasting (`occupancy.updated`, `density.updated`, `zone.updated`, `alert.created`, `device.status_changed`)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

import paho.mqtt.client as mqtt
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.entities import (
    Alert,
    DensityRecord,
    Device,
    DeviceStatusLog,
    OccupancyRecord,
    Room,
    SystemEvent,
    Zone,
)
from app.schemas.mqtt import (
    MqttAiTelemetryPayload,
    MqttAlertPayload,
    MqttCountPayload,
    MqttDensityPayload,
    MqttDeviceStatusPayload,
)
from app.websocket.manager import ws_manager

logger = logging.getLogger("backend.mqtt")


def classify_severity(
    count: int,
    max_capacity: int,
    density_per_sqm: float,
    warning_ratio: float,
    critical_density: float,
) -> str:
    """Evaluate crowd alert level (`NORMAL`, `WARNING`, `CRITICAL`)."""
    cap_ratio = count / max(1, max_capacity)
    if count > max_capacity or density_per_sqm >= critical_density:
        return "CRITICAL"
    if cap_ratio >= warning_ratio or density_per_sqm >= (critical_density * 0.70):
        return "WARNING"
    return "NORMAL"


class MqttAsyncWorker:
    """Manages Paho-MQTT connection, async message queue, and DB/WebSocket pipelines."""

    SUBSCRIBED_TOPICS: List[Tuple[str, int]] = [
        ("ai/rooms/+/telemetry", 1),
        ("occupancy/+/count", 1),
        ("occupancy/+/density", 1),
        ("occupancy/+/alerts", 1),
        ("occupancy/+/device/status", 1),
        ("iot/devices/+/status", 1),
    ]

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        dedup_window_sec: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._dedup_window_sec = dedup_window_sec
        self._queue: asyncio.Queue[Tuple[str, str, bool, float]] = asyncio.Queue(
            maxsize=2000
        )
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._client: Optional[mqtt.Client] = None
        self._connected: bool = False
        self._running: bool = False

        # In-memory state caches
        self._live_room_state: Dict[str, Dict[str, Any]] = {}
        self._dedup_hashes: Dict[str, float] = {}
        self._last_persisted_at: Dict[str, float] = {}
        self._reconnect_attempts: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def reconnect_attempts(self) -> int:
        return self._reconnect_attempts

    def get_live_room_state(self, room_key: str) -> Optional[Dict[str, Any]]:
        return self._live_room_state.get(room_key)

    async def start(self) -> None:
        """Start the async queue consumer and connect the Paho-MQTT client."""
        if self._running:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._worker_task = asyncio.create_task(
            self._consume_queue_loop(), name="mqtt-async-worker"
        )
        self._init_paho_client()

    async def stop(self) -> None:
        """Gracefully stop the background queue consumer and disconnect MQTT."""
        self._running = False
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        self._connected = False

        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    def _init_paho_client(self) -> None:
        client_id = f"{settings.MQTT_CLIENT_ID_PREFIX}_{uuid.uuid4().hex[:8]}"
        try:
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                clean_session=True,
            )
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id=client_id, clean_session=True)

        if settings.MQTT_USERNAME:
            client.username_pw_set(
                settings.MQTT_USERNAME, settings.MQTT_PASSWORD
            )

        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self._client = client

        try:
            client.connect_async(
                settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60
            )
            client.loop_start()
            logger.info(
                "Initiated async MQTT connection to %s:%d",
                settings.MQTT_HOST,
                settings.MQTT_PORT,
            )
        except Exception as exc:
            logger.warning(
                "MQTT broker initially unreachable (%s); auto-reconnect active.",
                exc,
            )

    def _on_connect(self, client, userdata, flags, rc, *args) -> None:
        rc_val = int(rc) if hasattr(rc, "__int__") else getattr(rc, "value", 0)
        if rc_val == 0:
            self._connected = True
            for topic, qos in self.SUBSCRIBED_TOPICS:
                client.subscribe(topic, qos=qos)
            logger.info(
                "Connected to MQTT broker and subscribed to %d topic patterns.",
                len(self.SUBSCRIBED_TOPICS),
            )
        else:
            self._connected = False
            logger.error("MQTT connection failed with rc=%s", rc)

    def _on_disconnect(self, client, userdata, *args) -> None:
        self._connected = False
        self._reconnect_attempts += 1
        logger.warning(
            "MQTT disconnected (reconnect_attempts=%d). Paho auto-reconnect engaged.",
            self._reconnect_attempts,
        )

    def _on_message(self, client, userdata, msg) -> None:
        """Non-blocking callback: decode UTF-8 and enqueue onto asyncio loop."""
        try:
            payload_str = msg.payload.decode("utf-8")
            retain_flag = bool(getattr(msg, "retain", False))
            topic = str(msg.topic)
        except Exception as exc:
            logger.warning("Failed to decode raw MQTT payload bytes: %s", exc)
            return

        if self._loop and self._running:
            self._loop.call_soon_threadsafe(
                self._enqueue_nowait,
                topic,
                payload_str,
                retain_flag,
                time.monotonic(),
            )

    def _enqueue_nowait(
        self, topic: str, payload_str: str, retain: bool, ts: float
    ) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait((topic, payload_str, retain, ts))

    def publish_json(
        self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False
    ) -> bool:
        """Publish JSON message to MQTT broker if connected."""
        if self._client is None or not self._connected:
            return False
        try:
            encoded = json.dumps(payload)
            info = self._client.publish(topic, encoded, qos=qos, retain=retain)
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as exc:
            logger.error("MQTT publish error on topic %s: %s", topic, exc)
            return False

    def publish_room_config(self, room: Room, zones: List[Zone]) -> bool:
        """Publish updated Room & Polygon Zone calibration to `ai/rooms/{code}/config`."""
        payload = {
            "roomId": room.id,
            "roomCode": room.code,
            "name": room.name,
            "roomName": room.name,
            "areaSqm": room.area_sqm,
            "maxCapacity": room.max_capacity,
            "warningThresholdRatio": room.warning_threshold_ratio,
            "criticalDensityPerSqm": room.critical_density_per_sqm,
            "zones": [
                {
                    "id": z.id,
                    "name": z.name,
                    "code": z.code,
                    "polygonCoordinates": z.polygon_coordinates,
                    "polygonPoints": z.polygon_coordinates,
                    "areaSqm": z.area_sqm,
                    "maxCapacity": z.max_capacity,
                    "warningDensity": z.warning_density,
                    "warningDensityThreshold": z.warning_density,
                    "criticalDensity": z.critical_density,
                    "criticalDensityThreshold": z.critical_density,
                    "colorHex": z.color_hex,
                }
                for z in zones
            ],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        return self.publish_json(
            f"ai/rooms/{room.code}/config", payload, qos=1, retain=True
        )

    def publish_device_command(
        self,
        room_code: str,
        device_code: str,
        command: Dict[str, Any],
    ) -> bool:
        """Publish actuation command to both room-scoped and device-scoped MQTT topics."""
        led_val = str(
            command.get("ledState")
            or command.get("led_state")
            or command.get("led")
            or "GREEN"
        ).upper()
        buz_val = bool(
            command.get("buzzerActive")
            if "buzzerActive" in command
            else (
                command.get("buzzer_active")
                if "buzzer_active" in command
                else command.get("buzzer", False)
            )
        )
        payload = {
            "action": command.get("action", "SET_STATE"),
            "deviceId": device_code,
            "roomId": room_code,
            "led": led_val,
            "ledState": led_val,
            "buzzer": buz_val,
            "buzzerActive": buz_val,
            **command,
            "issuedAt": datetime.now(timezone.utc).isoformat(),
        }
        ok1 = self.publish_json(
            f"occupancy/{room_code}/device/command", payload, qos=1
        )
        ok2 = self.publish_json(
            f"iot/devices/{device_code}/command", payload, qos=1
        )
        return ok1 or ok2

    async def _consume_queue_loop(self) -> None:
        while self._running:
            try:
                topic, payload_str, retain, ts = await self._queue.get()
                try:
                    await self.process_raw_message(
                        topic=topic,
                        payload_str=payload_str,
                        retain=retain,
                        received_monotonic=ts,
                    )
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error in MQTT worker loop: %s", exc)

    def _is_duplicate_message(
        self, topic: str, payload_str: str, now_mono: float
    ) -> bool:
        """Filter identical burst messages arriving within `dedup_window_sec`."""
        if self._dedup_window_sec <= 0:
            return False
        digest = hashlib.sha256(
            f"{topic}|{payload_str}".encode("utf-8")
        ).hexdigest()
        prev_ts = self._dedup_hashes.get(digest)
        self._dedup_hashes[digest] = now_mono

        # Prune expired hashes periodically
        if len(self._dedup_hashes) > 1000:
            cutoff = now_mono - (self._dedup_window_sec * 3)
            self._dedup_hashes = {
                k: v for k, v in self._dedup_hashes.items() if v >= cutoff
            }

        if prev_ts is not None and (now_mono - prev_ts) < self._dedup_window_sec:
            return True
        return False

    async def process_raw_message(
        self,
        topic: str,
        payload_str: str,
        retain: bool = False,
        received_monotonic: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validate and process a single MQTT message.
        Can be called directly in unit/integration tests or from the async queue.
        """
        now_mono = (
            received_monotonic
            if received_monotonic is not None
            else time.monotonic()
        )

        # 1. Duplicate burst filter
        if self._is_duplicate_message(topic, payload_str, now_mono):
            return {"status": "skipped_duplicate", "topic": topic}

        # 2. Parse JSON
        try:
            raw_data = json.loads(payload_str)
            if not isinstance(raw_data, dict):
                raise ValueError("JSON root must be an object.")
        except Exception as exc:
            self._record_invalid_payload(topic, payload_str, str(exc))
            return {"status": "invalid_json", "topic": topic, "error": str(exc)}

        # 3. Route by topic pattern & validate with Pydantic v2
        parts = topic.split("/")
        try:
            if (
                len(parts) == 4
                and parts[0] == "ai"
                and parts[1] == "rooms"
                and parts[3] == "telemetry"
            ):
                validated = MqttAiTelemetryPayload.model_validate(raw_data)
                return await self._handle_ai_telemetry(
                    room_identifier=parts[2],
                    payload=validated,
                    retain=retain,
                    now_mono=now_mono,
                )

            if (
                len(parts) == 3
                and parts[0] == "occupancy"
                and parts[2] == "count"
            ):
                validated_cnt = MqttCountPayload.model_validate(raw_data)
                return await self._handle_occupancy_count(
                    room_identifier=parts[1],
                    payload=validated_cnt,
                    retain=retain,
                    now_mono=now_mono,
                )

            if (
                len(parts) == 3
                and parts[0] == "occupancy"
                and parts[2] == "density"
            ):
                validated_den = MqttDensityPayload.model_validate(raw_data)
                return await self._handle_occupancy_density(
                    room_identifier=parts[1],
                    payload=validated_den,
                    retain=retain,
                    now_mono=now_mono,
                )

            if (
                len(parts) == 3
                and parts[0] == "occupancy"
                and parts[2] == "alerts"
            ):
                validated_al = MqttAlertPayload.model_validate(raw_data)
                return await self._handle_alert_message(
                    room_identifier=parts[1],
                    payload=validated_al,
                    retain=retain,
                )

            if (
                len(parts) == 4
                and parts[0] == "occupancy"
                and parts[2] == "device"
                and parts[3] == "status"
            ) or (
                len(parts) == 4
                and parts[0] == "iot"
                and parts[1] == "devices"
                and parts[3] == "status"
            ):
                validated_dev = MqttDeviceStatusPayload.model_validate(raw_data)
                return await self._handle_device_status(
                    payload=validated_dev,
                    raw_data=raw_data,
                    retain=retain,
                )

            return {"status": "ignored_topic", "topic": topic}

        except ValidationError as exc:
            self._record_invalid_payload(topic, payload_str, str(exc))
            return {
                "status": "validation_error",
                "topic": topic,
                "error": exc.errors(),
            }
        except SQLAlchemyError as db_exc:
            logger.error(
                "Database connection error while processing MQTT topic '%s': %s. Continuing with in-memory & WebSocket fallback.",
                topic,
                db_exc,
            )
            fallback_room = parts[2] if parts[0] == "ai" and len(parts) > 2 else (parts[1] if len(parts) > 1 else "room1")
            fallback_snapshot = {
                "room_id": fallback_room,
                "room_code": fallback_room,
                "current_count": int(raw_data.get("totalCount", raw_data.get("current_count", raw_data.get("count", 0)))),
                "overall_density": float(raw_data.get("roomDensity", raw_data.get("overallDensity", raw_data.get("overall_density", 0.0)))),
                "room_status": str(raw_data.get("roomStatus", raw_data.get("roomDensityLevel", "NORMAL"))),
                "retained": retain,
                "db_degraded": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._live_room_state[fallback_room] = fallback_snapshot
            await ws_manager.broadcast_event(
                "occupancy.updated", fallback_snapshot, room_id=fallback_room
            )
            return {
                "status": "db_degraded",
                "topic": topic,
                "error": str(db_exc),
            }

    def _record_invalid_payload(
        self, topic: str, payload_str: str, error_msg: str
    ) -> None:
        logger.warning(
            "Malformed MQTT payload on topic '%s': %s", topic, error_msg
        )
        db = self._session_factory()
        try:
            event = SystemEvent(
                event_type="MQTT_INVALID_PAYLOAD",
                severity="WARNING",
                source="MQTT_WORKER",
                message=f"Invalid payload on topic '{topic}': {error_msg}",
                details={"topic": topic, "raw_payload": payload_str[:1000]},
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            db.commit()
        except Exception as db_exc:
            db.rollback()
            logger.error("Failed to log system event: %s", db_exc)
        finally:
            db.close()

    def _resolve_room(self, db: Session, identifier: str) -> Optional[Room]:
        return (
            db.query(Room)
            .filter((Room.id == identifier) | (Room.code == identifier))
            .first()
        )

    async def _handle_ai_telemetry(
        self,
        room_identifier: str,
        payload: MqttAiTelemetryPayload,
        retain: bool,
        now_mono: float,
    ) -> Dict[str, Any]:
        db = self._session_factory()
        try:
            room = self._resolve_room(db, room_identifier) or self._resolve_room(
                db, payload.roomId
            )
            if not room:
                return {"status": "room_not_found", "room": room_identifier}

            overall_density = (
                payload.overallDensity
                if payload.overallDensity > 0
                else round(payload.totalCount / max(1.0, room.area_sqm), 4)
            )
            cap_ratio = round(
                payload.totalCount / max(1, room.max_capacity), 4
            )
            computed_status = classify_severity(
                count=payload.totalCount,
                max_capacity=room.max_capacity,
                density_per_sqm=overall_density,
                warning_ratio=room.warning_threshold_ratio,
                critical_density=room.critical_density_per_sqm,
            )
            if payload.roomStatus in ("WARNING", "CRITICAL") and computed_status == "NORMAL":
                room_status = payload.roomStatus
            else:
                room_status = computed_status

            state_snapshot = {
                "room_id": room.id,
                "room_code": room.code,
                "room_name": room.name,
                "current_count": payload.totalCount,
                "in_count": payload.inCount,
                "out_count": payload.outCount,
                "overall_density": overall_density,
                "capacity_ratio": cap_ratio,
                "room_status": room_status,
                "inference_fps": payload.fps,
                "zones": [z.model_dump() for z in payload.zones],
                "heatmap_grid": payload.heatmapGrid,
                "retained": retain,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._live_room_state[room.id] = state_snapshot
            self._live_room_state[room.code] = state_snapshot

            persisted = False
            created_alerts: List[Dict[str, Any]] = []

            # Only persist historical time-series & trigger new alerts for non-retained realtime messages
            if not retain:
                last_ts = self._last_persisted_at.get(room.id, 0.0)
                if (now_mono - last_ts) >= settings.OCCUPANCY_LOG_INTERVAL_SEC or last_ts == 0.0:
                    self._last_persisted_at[room.id] = now_mono
                    occ_rec = OccupancyRecord(
                        room_id=room.id,
                        total_count=payload.totalCount,
                        in_count=payload.inCount,
                        out_count=payload.outCount,
                        overall_density=overall_density,
                        capacity_ratio=cap_ratio,
                        room_status=room_status,
                        inference_fps=payload.fps,
                        recorded_at=datetime.now(timezone.utc),
                    )
                    db.add(occ_rec)

                    # Persist per-zone density records
                    zones_by_code = {
                        z.code: z
                        for z in db.query(Zone).filter(Zone.room_id == room.id).all()
                    }
                    for zm in payload.zones:
                        zone_entity = zones_by_code.get(zm.zoneCode)
                        if zone_entity:
                            den_val = round(
                                zm.count / max(0.5, zone_entity.area_sqm), 4
                            )
                            z_cap_ratio = round(
                                zm.count / max(1, zone_entity.max_capacity), 4
                            )
                            z_sev = classify_severity(
                                count=zm.count,
                                max_capacity=zone_entity.max_capacity,
                                density_per_sqm=den_val,
                                warning_ratio=0.75,
                                critical_density=zone_entity.critical_density,
                            )
                            db.add(
                                DensityRecord(
                                    room_id=room.id,
                                    zone_id=zone_entity.id,
                                    person_count=zm.count,
                                    density_per_sqm=den_val,
                                    capacity_ratio=z_cap_ratio,
                                    severity=z_sev,
                                    recorded_at=datetime.now(timezone.utc),
                                )
                            )
                    db.commit()
                    persisted = True

                # Evaluate alert creation & IoT actuation
                if room_status in ("WARNING", "CRITICAL"):
                    alert_obj = self._create_alert_if_needed(
                        db=db,
                        room=room,
                        alert_type="CROWD_DENSITY_THRESHOLD",
                        severity=room_status,
                        person_count=payload.totalCount,
                        density_value=overall_density,
                        threshold_value=room.critical_density_per_sqm,
                        message=(
                            f"Room '{room.name}' reached {room_status}: "
                            f"{payload.totalCount}/{room.max_capacity} people "
                            f"(density={overall_density:.3f} p/m²)."
                        ),
                    )
                    if alert_obj:
                        created_alerts.append(alert_obj)

                self._actuate_iot_for_room(db, room, room_status)

            # Broadcast WebSocket realtime events
            await ws_manager.broadcast_event(
                "occupancy.updated", state_snapshot, room_id=room.id
            )
            await ws_manager.broadcast_event(
                "density.updated",
                {
                    "room_id": room.id,
                    "room_code": room.code,
                    "overall_density": overall_density,
                    "capacity_ratio": cap_ratio,
                    "room_status": room_status,
                    "zones": state_snapshot["zones"],
                },
                room_id=room.id,
            )
            if state_snapshot["zones"]:
                await ws_manager.broadcast_event(
                    "zone.updated",
                    {"room_id": room.id, "zones": state_snapshot["zones"]},
                    room_id=room.id,
                )
            for al in created_alerts:
                await ws_manager.broadcast_event(
                    "alert.created", al, room_id=room.id
                )

            return {
                "status": "processed",
                "retained": retain,
                "persisted": persisted,
                "room_status": room_status,
            }
        finally:
            db.close()

    async def _handle_occupancy_count(
        self,
        room_identifier: str,
        payload: MqttCountPayload,
        retain: bool,
        now_mono: float,
    ) -> Dict[str, Any]:
        db = self._session_factory()
        try:
            room = self._resolve_room(db, room_identifier) or self._resolve_room(
                db, payload.room_id
            )
            if not room:
                return {"status": "room_not_found", "room": room_identifier}

            overall_density = round(
                payload.current_count / max(1.0, room.area_sqm), 4
            )
            cap_ratio = (
                payload.capacity_ratio
                if payload.capacity_ratio is not None
                else round(payload.current_count / max(1, room.max_capacity), 4)
            )
            room_status = classify_severity(
                count=payload.current_count,
                max_capacity=room.max_capacity,
                density_per_sqm=overall_density,
                warning_ratio=room.warning_threshold_ratio,
                critical_density=room.critical_density_per_sqm,
            )

            snapshot = self._live_room_state.get(room.id, {})
            snapshot.update(
                {
                    "room_id": room.id,
                    "room_code": room.code,
                    "room_name": room.name,
                    "current_count": payload.current_count,
                    "in_count": payload.in_count,
                    "out_count": payload.out_count,
                    "overall_density": overall_density,
                    "capacity_ratio": cap_ratio,
                    "room_status": room_status,
                    "retained": retain,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._live_room_state[room.id] = snapshot
            self._live_room_state[room.code] = snapshot

            persisted = False
            if not retain:
                last_ts = self._last_persisted_at.get(room.id, 0.0)
                if (now_mono - last_ts) >= settings.OCCUPANCY_LOG_INTERVAL_SEC or last_ts == 0.0:
                    self._last_persisted_at[room.id] = now_mono
                    db.add(
                        OccupancyRecord(
                            room_id=room.id,
                            total_count=payload.current_count,
                            in_count=payload.in_count,
                            out_count=payload.out_count,
                            overall_density=overall_density,
                            capacity_ratio=cap_ratio,
                            room_status=room_status,
                            recorded_at=datetime.now(timezone.utc),
                        )
                    )
                    db.commit()
                    persisted = True

                if room_status in ("WARNING", "CRITICAL"):
                    al = self._create_alert_if_needed(
                        db=db,
                        room=room,
                        alert_type="OCCUPANCY_LIMIT_EXCEEDED",
                        severity=room_status,
                        person_count=payload.current_count,
                        density_value=overall_density,
                        threshold_value=float(room.max_capacity),
                        message=f"Occupancy count {payload.current_count} reached {room_status} in {room.name}.",
                    )
                    if al:
                        await ws_manager.broadcast_event(
                            "alert.created", al, room_id=room.id
                        )

                self._actuate_iot_for_room(db, room, room_status)

            await ws_manager.broadcast_event(
                "occupancy.updated", snapshot, room_id=room.id
            )
            return {
                "status": "processed",
                "retained": retain,
                "persisted": persisted,
                "room_status": room_status,
            }
        finally:
            db.close()

    async def _handle_occupancy_density(
        self,
        room_identifier: str,
        payload: MqttDensityPayload,
        retain: bool,
        now_mono: float,
    ) -> Dict[str, Any]:
        db = self._session_factory()
        try:
            room = self._resolve_room(db, room_identifier) or self._resolve_room(
                db, payload.room_id
            )
            if not room:
                return {"status": "room_not_found", "room": room_identifier}

            persisted = False
            if not retain and payload.zones:
                zones_by_code = {
                    z.code: z
                    for z in db.query(Zone).filter(Zone.room_id == room.id).all()
                }
                for zm in payload.zones:
                    zone_entity = zones_by_code.get(zm.zoneCode)
                    if zone_entity:
                        den_val = (
                            zm.densityPerSqm
                            if zm.densityPerSqm > 0
                            else round(zm.count / max(0.5, zone_entity.area_sqm), 4)
                        )
                        cap_r = round(
                            zm.count / max(1, zone_entity.max_capacity), 4
                        )
                        sev = classify_severity(
                            count=zm.count,
                            max_capacity=zone_entity.max_capacity,
                            density_per_sqm=den_val,
                            warning_ratio=0.75,
                            critical_density=zone_entity.critical_density,
                        )
                        db.add(
                            DensityRecord(
                                room_id=room.id,
                                zone_id=zone_entity.id,
                                person_count=zm.count,
                                density_per_sqm=den_val,
                                capacity_ratio=cap_r,
                                severity=sev,
                                recorded_at=datetime.now(timezone.utc),
                            )
                        )
                db.commit()
                persisted = True

            data_out = {
                "room_id": room.id,
                "room_code": room.code,
                "overall_density": payload.overall_density,
                "alert_level": payload.alert_level,
                "zones": [z.model_dump() for z in payload.zones],
                "retained": retain,
            }
            await ws_manager.broadcast_event(
                "density.updated", data_out, room_id=room.id
            )
            if payload.zones:
                await ws_manager.broadcast_event(
                    "zone.updated",
                    {"room_id": room.id, "zones": data_out["zones"]},
                    room_id=room.id,
                )
            return {
                "status": "processed",
                "retained": retain,
                "persisted": persisted,
            }
        finally:
            db.close()

    async def _handle_alert_message(
        self,
        room_identifier: str,
        payload: MqttAlertPayload,
        retain: bool,
    ) -> Dict[str, Any]:
        if retain:
            return {"status": "skipped_retained_alert"}

        db = self._session_factory()
        try:
            room = self._resolve_room(db, room_identifier)
            if not room and (payload.room_id or payload.roomId):
                room = self._resolve_room(
                    db, str(payload.room_id or payload.roomId)
                )
            if not room:
                return {"status": "room_not_found"}

            zone_id = None
            if payload.zoneCode:
                z = (
                    db.query(Zone)
                    .filter(
                        Zone.room_id == room.id,
                        Zone.code == payload.zoneCode,
                    )
                    .first()
                )
                if z:
                    zone_id = z.id

            alert_dict = self._create_alert_if_needed(
                db=db,
                room=room,
                alert_type=payload.alertType,
                severity=payload.severity.upper(),
                person_count=payload.personCount,
                density_value=payload.densityValue,
                threshold_value=payload.thresholdValue,
                message=payload.message,
                zone_id=zone_id,
            )
            if alert_dict:
                await ws_manager.broadcast_event(
                    "alert.created", alert_dict, room_id=room.id
                )
            return {"status": "processed", "alert": alert_dict}
        finally:
            db.close()

    async def _handle_device_status(
        self,
        payload: MqttDeviceStatusPayload,
        raw_data: Dict[str, Any],
        retain: bool,
    ) -> Dict[str, Any]:
        db = self._session_factory()
        try:
            device = (
                db.query(Device)
                .filter(
                    (Device.device_code == payload.deviceId)
                    | (Device.id == payload.deviceId)
                )
                .first()
            )
            if not device:
                room = self._resolve_room(
                    db, payload.roomId or settings.INITIAL_ROOM_CODE
                )
                if not room:
                    return {"status": "room_not_found"}
                device = Device(
                    room_id=room.id,
                    device_code=payload.deviceId,
                    name=f"IoT Edge Node ({payload.deviceId})",
                    device_type="RASPBERRY_PI_EDGE",
                )
                db.add(device)
                db.flush()

            device.status = payload.status.upper()
            device.led_state = payload.ledState.upper()
            device.buzzer_active = payload.buzzerActive
            device.auto_mode = payload.autoMode
            if payload.gpioMode:
                device.gpio_mode = payload.gpioMode
            device.last_heartbeat = datetime.now(timezone.utc)

            if not retain:
                db.add(
                    DeviceStatusLog(
                        device_id=device.id,
                        status=device.status,
                        led_state=device.led_state,
                        buzzer_active=device.buzzer_active,
                        auto_mode=device.auto_mode,
                        person_count=payload.personCount,
                        density=payload.density,
                        raw_payload=raw_data,
                        logged_at=datetime.now(timezone.utc),
                    )
                )

            db.commit()
            db.refresh(device)

            event_data = {
                "id": device.id,
                "device_code": device.device_code,
                "room_id": device.room_id,
                "status": device.status,
                "led_state": device.led_state,
                "buzzer_active": device.buzzer_active,
                "auto_mode": device.auto_mode,
                "last_heartbeat": device.last_heartbeat.isoformat(),
            }
            await ws_manager.broadcast_event(
                "device.status_changed", event_data, room_id=device.room_id
            )
            return {"status": "processed", "device_code": device.device_code}
        finally:
            db.close()

    def _create_alert_if_needed(
        self,
        db: Session,
        room: Room,
        alert_type: str,
        severity: str,
        person_count: int,
        density_value: float,
        threshold_value: float,
        message: str,
        zone_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create an Alert if there is no unresolved alert of the same type/severity in the last 30s."""
        existing = (
            db.query(Alert)
            .filter(
                Alert.room_id == room.id,
                Alert.alert_type == alert_type,
                Alert.severity == severity,
                Alert.is_resolved.is_(False),
            )
            .order_by(Alert.triggered_at.desc())
            .first()
        )
        now = datetime.now(timezone.utc)
        if existing and existing.triggered_at:
            trig = existing.triggered_at
            if trig.tzinfo is None:
                trig = trig.replace(tzinfo=timezone.utc)
            if (now - trig).total_seconds() < 30.0:
                return None

        alert = Alert(
            room_id=room.id,
            zone_id=zone_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            person_count=person_count,
            density_value=density_value,
            threshold_value=threshold_value,
            is_acknowledged=False,
            is_resolved=False,
            triggered_at=now,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        return {
            "id": alert.id,
            "room_id": alert.room_id,
            "zone_id": alert.zone_id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "person_count": alert.person_count,
            "density_value": alert.density_value,
            "threshold_value": alert.threshold_value,
            "is_acknowledged": alert.is_acknowledged,
            "is_resolved": alert.is_resolved,
            "triggered_at": alert.triggered_at.isoformat(),
        }

    def _actuate_iot_for_room(
        self, db: Session, room: Room, room_status: str
    ) -> None:
        """Map `NORMAL`/`WARNING`/`CRITICAL` to Green/Yellow/Red LED & Buzzer when `auto_mode=True`."""
        devices = (
            db.query(Device)
            .filter(Device.room_id == room.id, Device.auto_mode.is_(True))
            .all()
        )
        if room_status == "CRITICAL":
            target_led, target_buzzer = "RED", True
        elif room_status == "WARNING":
            target_led, target_buzzer = "YELLOW", False
        else:
            target_led, target_buzzer = "GREEN", False

        for dev in devices:
            if dev.led_state != target_led or dev.buzzer_active != target_buzzer:
                dev.led_state = target_led
                dev.buzzer_active = target_buzzer
                db.commit()
                self.publish_device_command(
                    room_code=room.code,
                    device_code=dev.device_code,
                    command={
                        "ledState": target_led,
                        "buzzerActive": target_buzzer,
                        "autoMode": True,
                    },
                )


mqtt_worker = MqttAsyncWorker()
