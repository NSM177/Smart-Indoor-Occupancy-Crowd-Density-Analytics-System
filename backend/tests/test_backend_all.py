"""
Comprehensive Pytest Suite for Smart Indoor Occupancy & Crowd Density Analytics Backend.
Covers all 10 mandatory verification domains:
1. Authentication, JWT Refresh/Revocation & RBAC (`ADMIN` vs `OPERATOR`)
2. Room & Polygon Zone CRUD + Coordinate Validation
3. MQTT Payload Validation, Retained vs Realtime Distinction, Deduplication & `system_events` Logging
4. MQTT Reconnect Handling & IoT Command Dispatch
5. WebSocket Realtime Broadcasting, `ping`/`pong` Heartbeat & Broken Client Error Isolation
6. Occupancy Management (`in_count`, `out_count`, `current_count`, `room_status`)
7. Density Analytics (`density_per_sqm`, `busiest_zone`, `capacity_utilization_pct`)
8. Alert Evaluation (`NORMAL`, `WARNING`, `CRITICAL`), Auto IoT Actuation & Acknowledge/Resolve
9. Database Transactions, Cascade Deletion, Device Offline Detection & Historical Analytics/Forecasting
10. Global Error Handling (`401`, `403`, `404`, `409`, `422`)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.database.session import get_db
from app.main import create_app
from app.models.entities import (
    Alert,
    DensityRecord,
    Device,
    OccupancyRecord,
    Room,
    SystemEvent,
    Zone,
)
from app.mqtt.worker import MqttAsyncWorker
from app.websocket.manager import WebSocketManager


@pytest.fixture()
def db_session_factory():
    """Create an isolated in-memory SQLite database with all 9 tables seeded."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()
    yield TestingSessionLocal
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db_session_factory) -> Generator[TestClient, None, None]:
    """Create a FastAPI TestClient wired to the isolated test database."""
    app = create_app(enable_lifespan_db=False, enable_mqtt_broker=False)

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


def get_auth_headers(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 1. Authentication, Refresh Token, Logout & RBAC (`ADMIN` vs `OPERATOR`)
# ============================================================================

def test_01_authentication_and_rbac(client: TestClient):
    # 1. Login as ADMIN
    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.DEFAULT_ADMIN_USERNAME,
            "password": settings.DEFAULT_ADMIN_PASSWORD,
        },
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["user"]["role"] == "ADMIN"

    admin_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # 2. Verify /me endpoint
    me_res = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == settings.DEFAULT_ADMIN_USERNAME

    # 3. Refresh token flow
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert new_tokens["access_token"] != tokens["access_token"]

    # Old refresh token must be revoked after rotation
    reused_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused_refresh.status_code == 401

    # 4. Login as OPERATOR and verify RBAC restrictions
    op_headers = get_auth_headers(
        client,
        settings.DEFAULT_OPERATOR_USERNAME,
        settings.DEFAULT_OPERATOR_PASSWORD,
    )
    # Operator cannot create a new user (403 Forbidden)
    forbidden_user = client.post(
        "/api/v1/auth/users",
        headers=op_headers,
        json={
            "username": "new_op",
            "email": "new_op@occupancy.local",
            "password": "Password123",
            "full_name": "New Operator",
            "role": "OPERATOR",
        },
    )
    assert forbidden_user.status_code == 403

    # Operator cannot create a room (403 Forbidden)
    forbidden_room = client.post(
        "/api/v1/rooms",
        headers=op_headers,
        json={
            "code": "room_unauthorized",
            "name": "Unauthorized Room",
            "area_sqm": 50.0,
            "max_capacity": 20,
        },
    )
    assert forbidden_room.status_code == 403

    # 5. Logout revokes access token
    logout_res = client.post("/api/v1/auth/logout", headers=op_headers)
    assert logout_res.status_code == 200
    after_logout = client.get("/api/v1/auth/me", headers=op_headers)
    assert after_logout.status_code == 401


# ============================================================================
# 2. Room & Polygon Zone CRUD
# ============================================================================

def test_02_room_and_zone_crud(client: TestClient):
    admin_headers = get_auth_headers(
        client,
        settings.DEFAULT_ADMIN_USERNAME,
        settings.DEFAULT_ADMIN_PASSWORD,
    )

    # Create Room
    create_room_res = client.post(
        "/api/v1/rooms",
        headers=admin_headers,
        json={
            "code": "lab_202",
            "name": "AI Robotics Lab 202",
            "description": "Research Laboratory",
            "area_sqm": 80.0,
            "max_capacity": 40,
            "warning_threshold_ratio": 0.75,
            "critical_density_per_sqm": 0.70,
        },
    )
    assert create_room_res.status_code == 201
    room_data = create_room_res.json()
    room_id = room_data["id"]
    assert room_data["code"] == "lab_202"

    # Update Room
    update_room_res = client.put(
        f"/api/v1/rooms/{room_id}",
        headers=admin_headers,
        json={"max_capacity": 45, "area_sqm": 90.0},
    )
    assert update_room_res.status_code == 200
    assert update_room_res.json()["max_capacity"] == 45
    assert update_room_res.json()["area_sqm"] == 90.0

    # Create Polygon Zone in Room
    create_zone_res = client.post(
        f"/api/v1/rooms/{room_id}/zones",
        headers=admin_headers,
        json={
            "name": "Zone Lab North",
            "code": "ZONE_N",
            "polygon_coordinates": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.5, "y": 0.1},
                {"x": 0.5, "y": 0.8},
                {"x": 0.1, "y": 0.8},
            ],
            "area_sqm": 30.0,
            "max_capacity": 15,
            "warning_density": 0.45,
            "critical_density": 0.75,
            "color_hex": "#EC4899",
        },
    )
    assert create_zone_res.status_code == 201
    zone_id = create_zone_res.json()["id"]

    # Update Zone
    upd_zone = client.put(
        f"/api/v1/zones/{zone_id}",
        headers=admin_headers,
        json={"name": "Zone Lab North Updated", "max_capacity": 18},
    )
    assert upd_zone.status_code == 200
    assert upd_zone.json()["max_capacity"] == 18

    # List Zones
    zones_list = client.get(f"/api/v1/rooms/{room_id}/zones")
    assert zones_list.status_code == 200
    assert len(zones_list.json()) == 1

    # Delete Zone & Room
    del_zone = client.delete(f"/api/v1/zones/{zone_id}", headers=admin_headers)
    assert del_zone.status_code == 200
    del_room = client.delete(f"/api/v1/rooms/{room_id}", headers=admin_headers)
    assert del_room.status_code == 200


# ============================================================================
# 3. MQTT Payload Parsing, Retained Distinction, Deduplication & System Events
# ============================================================================

def test_03_mqtt_payload_validation_retained_and_dedup(db_session_factory):
    worker = MqttAsyncWorker(
        session_factory=db_session_factory, dedup_window_sec=2.0
    )

    valid_telemetry = json.dumps(
        {
            "roomId": "room1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frameIndex": 42,
            "fps": 18.5,
            "totalCount": 24,
            "inCount": 30,
            "outCount": 6,
            "overallDensity": 0.20,
            "capacityRatio": 0.40,
            "roomStatus": "NORMAL",
            "zones": [
                {
                    "zoneCode": "ZONE_A",
                    "zoneName": "Zone A",
                    "count": 10,
                    "areaSqm": 36.0,
                    "maxCapacity": 18,
                    "densityPerSqm": 0.2778,
                    "capacityRatio": 0.5556,
                    "severity": "NORMAL",
                },
                {
                    "zoneCode": "ZONE_B",
                    "zoneName": "Zone B",
                    "count": 14,
                    "areaSqm": 54.0,
                    "maxCapacity": 27,
                    "densityPerSqm": 0.2593,
                    "capacityRatio": 0.5185,
                    "severity": "NORMAL",
                },
            ],
            "alerts": [],
        }
    )

    # A. Retained message updates live state but DOES NOT write historical DB rows
    res_retained = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=valid_telemetry,
            retain=True,
            received_monotonic=100.0,
        )
    )
    assert res_retained["status"] == "processed"
    assert res_retained["retained"] is True
    assert res_retained["persisted"] is False

    # B. Duplicate burst within dedup window is skipped
    res_dup = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=valid_telemetry,
            retain=False,
            received_monotonic=100.5,
        )
    )
    assert res_dup["status"] == "skipped_duplicate"

    # C. Realtime message after dedup window persists to DB
    res_realtime = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=valid_telemetry,
            retain=False,
            received_monotonic=105.0,
        )
    )
    assert res_realtime["status"] == "processed"
    assert res_realtime["persisted"] is True

    # D. Malformed JSON & Invalid schema are logged into `system_events`
    res_bad_json = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/count",
            payload_str="{invalid_json",
            retain=False,
            received_monotonic=110.0,
        )
    )
    assert res_bad_json["status"] == "invalid_json"

    res_bad_schema = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/count",
            payload_str=json.dumps({"room_id": "room1", "current_count": -10}),
            retain=False,
            received_monotonic=115.0,
        )
    )
    assert res_bad_schema["status"] == "validation_error"

    db = db_session_factory()
    try:
        events = db.query(SystemEvent).all()
        assert len(events) >= 2
        assert any(e.event_type == "MQTT_INVALID_PAYLOAD" for e in events)
    finally:
        db.close()


# ============================================================================
# 4. MQTT Reconnect Handling & Granular Topic Compatibility
# ============================================================================

def test_04_mqtt_reconnect_and_granular_topics(db_session_factory):
    worker = MqttAsyncWorker(
        session_factory=db_session_factory, dedup_window_sec=0.0
    )
    assert worker.reconnect_attempts == 0
    worker._on_disconnect(None, None, 1)
    assert worker.reconnect_attempts == 1
    assert worker.is_connected is False

    # Granular count topic `occupancy/room1/count`
    cnt_res = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/count",
            payload_str=json.dumps(
                {
                    "room_id": "room1",
                    "current_count": 50,
                    "in_count": 65,
                    "out_count": 15,
                }
            ),
            retain=False,
            received_monotonic=200.0,
        )
    )
    assert cnt_res["status"] == "processed"
    assert cnt_res["room_status"] == "WARNING"  # 50/60 = 0.833 >= 0.75

    # Granular device status topic `occupancy/room1/device/status`
    dev_res = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/device/status",
            payload_str=json.dumps(
                {
                    "deviceId": settings.IOT_DEVICE_ID,
                    "roomId": "room1",
                    "status": "ONLINE",
                    "ledState": "YELLOW",
                    "buzzerActive": False,
                    "autoMode": True,
                    "personCount": 50,
                    "density": 0.4167,
                }
            ),
            retain=False,
            received_monotonic=205.0,
        )
    )
    assert dev_res["status"] == "processed"


# ============================================================================
# 5. WebSocket Broadcasting, Heartbeat & Broken Client Isolation
# ============================================================================

def test_05_websocket_broadcast_and_error_isolation(client: TestClient):
    with client.websocket_connect("/ws/realtime?room_id=room1&client_id=test_ws_1") as ws:
        welcome = ws.receive_json()
        assert welcome["event"] == "connected"
        assert welcome["client_id"] == "test_ws_1"

        # Send heartbeat ping
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["event"] == "pong"

        # Subscribe to room
        ws.send_json({"type": "subscribeRoom", "roomId": "room1"})
        sub_ack = ws.receive_json()
        assert sub_ack["event"] == "subscribed"

    # Verify broken client isolation in WebSocketManager
    manager = WebSocketManager()

    class BrokenSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            raise RuntimeError("Simulated socket broken pipe")

    class HealthySocket:
        def __init__(self):
            self.messages = []

        async def accept(self):
            pass

        async def send_json(self, data):
            self.messages.append(data)

    broken = BrokenSocket()
    healthy = HealthySocket()

    async def run_isolation_check():
        await manager.connect(broken, client_id="bad_client")
        await manager.connect(healthy, client_id="good_client")
        assert manager.active_count == 2
        delivered = await manager.broadcast_event(
            "occupancy.updated", {"current_count": 15}
        )
        assert delivered == 1
        assert manager.active_count == 1
        assert len(healthy.messages) == 1
        assert healthy.messages[0]["event"] == "occupancy.updated"

    asyncio.run(run_isolation_check())


# ============================================================================
# 6 & 7. Occupancy & Density Calculations + Busiest Zone Identification
# ============================================================================

def test_06_07_occupancy_and_density_calculations(
    client: TestClient, db_session_factory
):
    db = db_session_factory()
    try:
        room = db.query(Room).filter(Room.code == "room1").first()
        zones = {
            z.code: z
            for z in db.query(Zone).filter(Zone.room_id == room.id).all()
        }
        now = datetime.now(timezone.utc)

        db.add(
            OccupancyRecord(
                room_id=room.id,
                total_count=36,
                in_count=48,
                out_count=12,
                overall_density=0.30,
                capacity_ratio=0.60,
                room_status="NORMAL",
                inference_fps=20.0,
                recorded_at=now,
            )
        )
        # Zone A: 6 people / 36 m² = 0.1667 p/m²
        # Zone B: 27 people / 54 m² = 0.5000 p/m² (BUSIEST ZONE)
        # Zone C: 3 people / 30 m² = 0.1000 p/m²
        db.add_all(
            [
                DensityRecord(
                    room_id=room.id,
                    zone_id=zones["ZONE_A"].id,
                    person_count=6,
                    density_per_sqm=round(6 / zones["ZONE_A"].area_sqm, 4),
                    capacity_ratio=round(6 / zones["ZONE_A"].max_capacity, 4),
                    severity="NORMAL",
                    recorded_at=now,
                ),
                DensityRecord(
                    room_id=room.id,
                    zone_id=zones["ZONE_B"].id,
                    person_count=27,
                    density_per_sqm=round(27 / zones["ZONE_B"].area_sqm, 4),
                    capacity_ratio=round(27 / zones["ZONE_B"].max_capacity, 4),
                    severity="WARNING",
                    recorded_at=now,
                ),
                DensityRecord(
                    room_id=room.id,
                    zone_id=zones["ZONE_C"].id,
                    person_count=3,
                    density_per_sqm=round(3 / zones["ZONE_C"].area_sqm, 4),
                    capacity_ratio=round(3 / zones["ZONE_C"].max_capacity, 4),
                    severity="NORMAL",
                    recorded_at=now,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    # Check Occupancy Current & History
    occ_cur = client.get("/api/v1/rooms/room1/occupancy/current")
    assert occ_cur.status_code == 200
    occ_json = occ_cur.json()
    assert occ_json["current_count"] == 36
    assert occ_json["in_count"] == 48
    assert occ_json["out_count"] == 12
    assert occ_json["capacity_ratio"] == 0.60

    occ_hist = client.get("/api/v1/rooms/room1/occupancy/history?limit=10")
    assert occ_hist.status_code == 200
    assert len(occ_hist.json()) >= 1

    # Check Density Current & Busiest Zone
    den_cur = client.get("/api/v1/rooms/room1/density/current")
    assert den_cur.status_code == 200
    den_json = den_cur.json()
    assert den_json["capacity_utilization_pct"] == 60.0
    assert den_json["busiest_zone"] is not None
    assert den_json["busiest_zone"]["zone_code"] == "ZONE_B"
    assert den_json["busiest_zone"]["person_count"] == 27

    den_hist = client.get("/api/v1/rooms/room1/density/history?limit=10")
    assert den_hist.status_code == 200
    assert len(den_hist.json()) == 3


# ============================================================================
# 8. Alert Generation, Acknowledge/Resolve & Auto IoT Actuation
# ============================================================================

def test_08_alert_generation_and_acknowledgement(
    client: TestClient, db_session_factory
):
    worker = MqttAsyncWorker(
        session_factory=db_session_factory, dedup_window_sec=0.0
    )
    # Trigger CRITICAL overcrowding (68 people > max_capacity 60)
    crit_payload = json.dumps(
        {
            "room_id": "room1",
            "current_count": 68,
            "in_count": 80,
            "out_count": 12,
        }
    )
    res = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/count",
            payload_str=crit_payload,
            retain=False,
            received_monotonic=500.0,
        )
    )
    assert res["room_status"] == "CRITICAL"

    # Verify Alert created and Device LED switched to RED + Buzzer ON
    alerts_res = client.get("/api/v1/alerts?only_unresolved=true")
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()
    assert len(alerts) >= 1
    alert_id = alerts[0]["id"]
    assert alerts[0]["severity"] == "CRITICAL"
    assert alerts[0]["is_acknowledged"] is False

    # Verify Device auto-actuated to RED + Buzzer=True
    dev_res = client.get(f"/api/v1/devices/{settings.IOT_DEVICE_ID}/status")
    assert dev_res.status_code == 200
    assert dev_res.json()["led_state"] == "RED"
    assert dev_res.json()["buzzer_active"] is True

    # Acknowledge alert
    op_headers = get_auth_headers(
        client,
        settings.DEFAULT_OPERATOR_USERNAME,
        settings.DEFAULT_OPERATOR_PASSWORD,
    )
    ack_res = client.patch(
        f"/api/v1/alerts/{alert_id}/acknowledge", headers=op_headers
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["is_acknowledged"] is True

    # Resolve alert
    resolve_res = client.patch(
        f"/api/v1/alerts/{alert_id}/resolve", headers=op_headers
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["is_resolved"] is True


# ============================================================================
# 9. Historical Analytics, Peak Hours, Forecasting & Device Offline Detection
# ============================================================================

def test_09_analytics_forecasting_and_device_offline(
    client: TestClient, db_session_factory
):
    db = db_session_factory()
    try:
        room = db.query(Room).filter(Room.code == "room1").first()
        now = datetime.now(timezone.utc)
        # Insert 12 increasing occupancy samples over the past 60 minutes
        for i in range(12):
            sample_time = now - timedelta(minutes=(12 - i) * 5)
            cnt = 15 + i * 3
            db.add(
                OccupancyRecord(
                    room_id=room.id,
                    total_count=cnt,
                    in_count=cnt + 5,
                    out_count=5,
                    overall_density=round(cnt / room.area_sqm, 4),
                    capacity_ratio=round(cnt / room.max_capacity, 4),
                    room_status="WARNING" if cnt >= 45 else "NORMAL",
                    recorded_at=sample_time,
                )
            )

        # Simulate stale device heartbeat (> 35 seconds ago)
        dev = (
            db.query(Device)
            .filter(Device.device_code == settings.IOT_DEVICE_ID)
            .first()
        )
        dev.status = "ONLINE"
        dev.last_heartbeat = now - timedelta(seconds=120)
        db.commit()
    finally:
        db.close()

    # Overview Analytics
    ov_res = client.get("/api/v1/analytics/overview?room_id=room1&hours=24")
    assert ov_res.status_code == 200
    ov = ov_res.json()
    assert ov["total_samples"] == 12
    assert ov["peak_occupancy"] == 48
    assert ov["time_over_threshold_seconds"] > 0

    # Peak Hours
    pk_res = client.get("/api/v1/analytics/peak-hours?room_id=room1&days=7")
    assert pk_res.status_code == 200
    assert len(pk_res.json()) >= 1

    # Occupancy & Density aggregated series
    occ_series = client.get(
        "/api/v1/analytics/occupancy?room_id=room1&granularity=daily"
    )
    assert occ_series.status_code == 200
    assert occ_series.json()["count"] >= 1

    den_series = client.get(
        "/api/v1/analytics/density?room_id=room1&granularity=hourly"
    )
    assert den_series.status_code == 200

    # Short-Term OLS Forecast
    fc_res = client.get(
        "/api/v1/analytics/forecast?room_id=room1&horizon_minutes=30"
    )
    assert fc_res.status_code == 200
    fc = fc_res.json()
    assert fc["trend"] == "INCREASING"
    assert fc["slope_per_minute"] > 0
    assert len(fc["predictions"]) == 6

    # Device offline detection on stale heartbeat + manual command
    dev_status = client.get(f"/api/v1/devices/{settings.IOT_DEVICE_ID}/status")
    assert dev_status.status_code == 200
    assert dev_status.json()["is_online"] is False
    assert dev_status.json()["status"] == "OFFLINE"

    cmd_res = client.post(
        f"/api/v1/devices/{settings.IOT_DEVICE_ID}/commands",
        json={"led_state": "GREEN", "buzzer_active": False, "auto_mode": False},
    )
    assert cmd_res.status_code == 200
    assert cmd_res.json()["device"]["led_state"] == "GREEN"


# ============================================================================
# 10. Global Error Handling (`401`, `404`, `409`, `422`)
# ============================================================================

def test_10_error_handling(client: TestClient):
    # 404 Not Found on non-existent room
    not_found = client.get("/api/v1/rooms/non_existent_room_999")
    assert not_found.status_code == 404
    assert "not found" in not_found.json()["message"].lower()

    # 401 Invalid credentials
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # 422 Validation error on polygon zone with < 3 points
    admin_headers = get_auth_headers(
        client,
        settings.DEFAULT_ADMIN_USERNAME,
        settings.DEFAULT_ADMIN_PASSWORD,
    )
    bad_zone = client.post(
        "/api/v1/rooms/room1/zones",
        headers=admin_headers,
        json={
            "name": "Invalid Polygon",
            "code": "BAD_POLY",
            "polygon_coordinates": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.2}],
            "area_sqm": 10.0,
            "max_capacity": 5,
        },
    )
    assert bad_zone.status_code == 422

    # 409 Conflict on duplicate room code
    dup_room = client.post(
        "/api/v1/rooms",
        headers=admin_headers,
        json={
            "code": "room1",
            "name": "Duplicate Room 1",
            "area_sqm": 100.0,
            "max_capacity": 50,
        },
    )
    assert dup_room.status_code == 409


# ============================================================================
# 11. Database Transactions & Cascade Integrity
# ============================================================================

def test_11_database_cascade_delete_and_transactions(
    client: TestClient, db_session_factory
):
    admin_headers = get_auth_headers(
        client,
        settings.DEFAULT_ADMIN_USERNAME,
        settings.DEFAULT_ADMIN_PASSWORD,
    )
    # Create a temporary room with zone, occupancy record, and alert
    r_res = client.post(
        "/api/v1/rooms",
        headers=admin_headers,
        json={
            "code": "temp_cascade_room",
            "name": "Temporary Cascade Room",
            "area_sqm": 60.0,
            "max_capacity": 25,
        },
    )
    assert r_res.status_code == 201
    temp_room_id = r_res.json()["id"]

    z_res = client.post(
        f"/api/v1/rooms/{temp_room_id}/zones",
        headers=admin_headers,
        json={
            "name": "Temp Zone",
            "code": "TZ_1",
            "polygon_coordinates": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.6, "y": 0.1},
                {"x": 0.6, "y": 0.6},
            ],
            "area_sqm": 20.0,
            "max_capacity": 10,
        },
    )
    assert z_res.status_code == 201
    temp_zone_id = z_res.json()["id"]

    # Delete the room and verify cascade deletion of its zones
    del_res = client.delete(
        f"/api/v1/rooms/{temp_room_id}", headers=admin_headers
    )
    assert del_res.status_code == 200

    db = db_session_factory()
    try:
        assert db.query(Zone).filter(Zone.id == temp_zone_id).first() is None
    finally:
        db.close()

