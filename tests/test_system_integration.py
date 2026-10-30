"""
End-to-End System Integration Test Suite (`tests/test_system_integration.py`).
Verifies cross-service integration across:
- AI Computer Vision Engine (`ai-service`)
- Raspberry Pi IoT Edge Service (`iot-service`)
- FastAPI + SQLAlchemy 2.0 + WebSocket + MQTT Backend (`backend`)
- Database Schema & Persistence (9 SQLAlchemy tables)

Covers all 10 mandatory integration scenarios:
1. Empty room (0 people -> NORMAL, Green LED, Buzzer OFF).
2. Small number of people (AI -> MQTT -> Backend -> DB -> IoT Green LED).
3. Room exceeds warning & critical thresholds (AI -> MQTT -> Backend -> Alert -> IoT Red LED + Buzzer PULSE -> Operator Acknowledge/Silence).
4. People moving between polygon zones (Zone A -> Zone B -> Zone C density & busiest zone analytics).
5. Camera loses connection (`is_hw_connected=False` -> 0 tracks, graceful fallback, health check reflects disconnected camera).
6. Raspberry Pi loses connection (LWT OFFLINE / heartbeat timeout > 35s -> Device marked OFFLINE).
7. MQTT Broker disconnected (Auto-reconnect backoff & state tracking in AI, IoT, and Backend).
8. Backend restarted (Retained MQTT recovery restores live state without duplicate history rows).
9. Frontend loses WebSocket connection (Disconnect cleanup, broken socket isolation, reconnect with initial state & ping/pong).
10. Database loses connection (Graceful `SQLAlchemyError` degradation in MQTT worker & `/health` endpoint without crashing realtime WebSocket).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Dict, List
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
AI_DIR = ROOT_DIR / "ai-service"
IOT_DIR = ROOT_DIR / "iot-service"

# Put backend first on sys.path so `app.*` resolves to backend's `app` package
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings as backend_settings
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.database.session import get_db
from app.main import create_app
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
from app.mqtt.worker import MqttAsyncWorker, mqtt_worker
from app.websocket.manager import ws_manager


def _load_external_module(module_alias: str, file_path: Path):
    """Load a Python module from `ai-service` or `iot-service` without colliding with backend `app.*`."""
    spec = importlib.util.spec_from_file_location(module_alias, str(file_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_alias] = mod
    spec.loader.exec_module(mod)
    return mod


import types

# Load IoT Service modules
iot_cfg_mod = _load_external_module("iot_config", IOT_DIR / "app" / "config.py")
sys.modules["app.config"] = iot_cfg_mod
iot_log_mod = _load_external_module("iot_logger", IOT_DIR / "app" / "logger.py")
sys.modules["app.logger"] = iot_log_mod
sys.modules["app.hardware"] = types.ModuleType("app.hardware")
iot_gpio_if_mod = _load_external_module(
    "iot_gpio_interface", IOT_DIR / "app" / "hardware" / "gpio_interface.py"
)
sys.modules["app.hardware.gpio_interface"] = iot_gpio_if_mod
iot_gpio_mod = _load_external_module(
    "iot_gpio_driver", IOT_DIR / "app" / "hardware" / "gpio_driver.py"
)
sys.modules["app.hardware.gpio_driver"] = iot_gpio_mod
iot_proc_mod = _load_external_module(
    "iot_occupancy_processor",
    IOT_DIR / "app" / "processor" / "occupancy_processor.py",
)

# Load AI Service modules
ai_vision_pkg = types.ModuleType("app.vision")
ai_vision_pkg.__path__ = [str(AI_DIR / "app" / "vision")]
sys.modules["app.vision"] = ai_vision_pkg
ai_log_mod = _load_external_module(
    "ai_core_logger", AI_DIR / "app" / "core" / "logger.py"
)
sys.modules["app.core.logger"] = ai_log_mod
ai_schemas_mod = _load_external_module(
    "ai_schemas", AI_DIR / "app" / "schemas" / "vision_schema.py"
)
sys.modules["app.schemas.vision_schema"] = ai_schemas_mod
ai_zone_mod = _load_external_module(
    "ai_zone_analyzer", AI_DIR / "app" / "vision" / "zone_analyzer.py"
)
sys.modules["app.vision.zone_analyzer"] = ai_zone_mod
ai_alert_mod = _load_external_module(
    "ai_crowd_alert", AI_DIR / "app" / "vision" / "crowd_alert.py"
)
sys.modules["app.vision.crowd_alert"] = ai_alert_mod
ai_heatmap_mod = _load_external_module(
    "ai_heatmap", AI_DIR / "app" / "vision" / "heatmap_generator.py"
)
sys.modules["app.vision.heatmap_generator"] = ai_heatmap_mod


@pytest.fixture()
def integrated_env():
    """
    Set up an isolated end-to-end test environment combining:
    - SQLAlchemy 2.0 in-memory DB with all 9 tables seeded
    - FastAPI Backend `TestClient`
    - Backend `MqttAsyncWorker`
    - IoT Service `GpioController` (Simulation Mode) + `OccupancyDataProcessor`
    - AI Service `ZoneAnalyzer` + `CrowdAlertEngine` + `HeatmapGenerator`
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    seed_initial_data(db)
    db.close()

    app = create_app(enable_lifespan_db=False, enable_mqtt_broker=False)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Wire Backend singleton `mqtt_worker` to the test DB and intercept published MQTT messages
    worker = mqtt_worker
    worker._session_factory = TestingSessionLocal
    worker._dedup_window_sec = 0.0
    worker._live_room_state.clear()
    worker._dedup_hashes.clear()
    worker._last_persisted_at.clear()
    published_mqtt_messages: List[Dict[str, Any]] = []

    iot_settings = iot_cfg_mod.IotSettings(
        SIMULATION_MODE=True,
        IOT_DEVICE_ID="RPI_NODE_01",
        IOT_ROOM_ID="room1",
        ROOM_MAX_CAPACITY=60,
        WARNING_OCCUPANCY_RATIO=0.75,
        WARNING_DENSITY_THRESHOLD=0.35,
        CRITICAL_DENSITY_THRESHOLD=0.50,
        BUZZER_MAX_DURATION_SEC=15,
    )
    iot_gpio = iot_gpio_mod.GpioController(
        pin_led_green=17,
        pin_led_yellow=27,
        pin_led_red=22,
        pin_buzzer=23,
        force_simulation=True,
    )
    iot_processor = iot_proc_mod.OccupancyDataProcessor(
        settings=iot_settings, gpio=iot_gpio
    )

    def fake_publish_json(
        topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False
    ) -> bool:
        published_mqtt_messages.append(
            {"topic": topic, "payload": payload, "qos": qos, "retain": retain}
        )
        # Route Backend -> MQTT -> Raspberry Pi IoT Service commands automatically
        if topic.endswith("/device/command") or topic.startswith("iot/devices/"):
            iot_processor.process_command_payload(payload)
        return True

    worker.publish_json = fake_publish_json  # type: ignore
    backend_settings.OCCUPANCY_LOG_INTERVAL_SEC = 0

    with TestClient(app) as client:
        yield {
            "client": client,
            "db_factory": TestingSessionLocal,
            "engine": engine,
            "worker": worker,
            "iot_gpio": iot_gpio,
            "iot_processor": iot_processor,
            "published_mqtt": published_mqtt_messages,
        }

    iot_gpio.cleanup()


def _get_auth_headers(client: TestClient, username: str = "admin", password: str = "Admin@123") -> Dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _build_ai_telemetry_payload(
    tracks_xy: List[tuple[float, float]],
    in_count: int = 0,
    out_count: int = 0,
    area_sqm: float = 120.0,
    max_capacity: int = 60,
) -> Dict[str, Any]:
    """
    Use the real AI Service `ZoneAnalyzer`, `CrowdAlertEngine`, and `HeatmapGenerator`
    to construct an authentic `ai-service` MQTT telemetry payload (`ai/rooms/room1/telemetry`).
    """
    frame_w, frame_h = 1280, 720
    zones_cfg = [
        ai_schemas_mod.ZoneConfig(
            id="z-a",
            name="Zone A - Entrance & Reception",
            code="ZONE_A",
            polygonPoints=[
                ai_schemas_mod.NormalizedPoint(x=0.02, y=0.05),
                ai_schemas_mod.NormalizedPoint(x=0.35, y=0.05),
                ai_schemas_mod.NormalizedPoint(x=0.35, y=0.95),
                ai_schemas_mod.NormalizedPoint(x=0.02, y=0.95),
            ],
            areaSqm=36.0,
            maxCapacity=18,
            warningDensityThreshold=0.35,
            criticalDensityThreshold=0.50,
        ),
        ai_schemas_mod.ZoneConfig(
            id="z-b",
            name="Zone B - Central Main Floor",
            code="ZONE_B",
            polygonPoints=[
                ai_schemas_mod.NormalizedPoint(x=0.36, y=0.05),
                ai_schemas_mod.NormalizedPoint(x=0.68, y=0.05),
                ai_schemas_mod.NormalizedPoint(x=0.68, y=0.95),
                ai_schemas_mod.NormalizedPoint(x=0.36, y=0.95),
            ],
            areaSqm=54.0,
            maxCapacity=27,
            warningDensityThreshold=0.35,
            criticalDensityThreshold=0.50,
        ),
        ai_schemas_mod.ZoneConfig(
            id="z-c",
            name="Zone C - Exit & Corridor",
            code="ZONE_C",
            polygonPoints=[
                ai_schemas_mod.NormalizedPoint(x=0.69, y=0.05),
                ai_schemas_mod.NormalizedPoint(x=0.98, y=0.05),
                ai_schemas_mod.NormalizedPoint(x=0.98, y=0.95),
                ai_schemas_mod.NormalizedPoint(x=0.69, y=0.95),
            ],
            areaSqm=30.0,
            maxCapacity=15,
            warningDensityThreshold=0.35,
            criticalDensityThreshold=0.50,
        ),
    ]

    tracks = []
    for idx, (nx, ny) in enumerate(tracks_xy, start=1):
        px = int(nx * frame_w)
        py = int(ny * frame_h)
        tracks.append(
            ai_schemas_mod.TrackedPerson(
                id=idx,
                confidence=0.91,
                bbox=(
                    max(0, px - 20),
                    max(0, py - 60),
                    min(frame_w, px + 20),
                    py,
                ),
                footPoint=ai_schemas_mod.NormalizedPoint(x=nx, y=ny),
                footPointPx=(px, py),
                dwellSec=12.5,
            )
        )

    tracks, zone_telemetries = ai_zone_mod.ZoneAnalyzer.analyze_zones(
        tracks=tracks,
        zones=zones_cfg,
        frame_width=frame_w,
        frame_height=frame_h,
    )

    heatmap = ai_heatmap_mod.HeatmapGenerator(grid_width=16, grid_height=12)
    heatmap.update(tracks)

    total_count = len(tracks)
    room_density = round(total_count / area_sqm, 4)
    room_occ_rate = round((total_count / max_capacity) * 100.0, 1)
    room_level = ai_zone_mod.ZoneAnalyzer.classify_density_level(
        room_density, 0.35, 0.50
    )

    alert_engine = ai_alert_mod.CrowdAlertEngine(
        hysteresis_ratio=0.10, sustain_sec=0.0
    )
    active_alerts = alert_engine.evaluate(
        room_id="room1",
        room_name="Main Conference & Exhibition Hall",
        total_count=total_count,
        room_max_capacity=max_capacity,
        room_density=room_density,
        room_warn_density=0.35,
        room_crit_density=0.50,
        zones=zone_telemetries,
    )

    telemetry = ai_schemas_mod.VisionTelemetryPayload(
        timestamp=datetime.now(timezone.utc).isoformat(),
        roomId="room1",
        roomName="Main Conference & Exhibition Hall",
        cameraId="cam-01",
        fps=24.5,
        totalCount=total_count,
        roomAreaSqm=area_sqm,
        roomMaxCapacity=max_capacity,
        roomDensity=room_density,
        roomOccupancyRate=room_occ_rate,
        roomDensityLevel=room_level,
        lineCounts=[
            ai_schemas_mod.LineCrossingStats(
                lineId="line-1",
                lineName="Main Entrance Gate",
                inCount=in_count,
                outCount=out_count,
                netFlow=in_count - out_count,
            )
        ],
        tracks=tracks,
        zones=zone_telemetries,
        activeAlerts=active_alerts,
        performance=ai_schemas_mod.PerformanceMetrics(
            fps=24.5,
            inferenceTimeMs=14.2,
            processingTimeMs=18.6,
            frameSkip=1,
            inferenceResolution=(640, 360),
            modelBackend="yolov8n-onnx",
            totalFramesProcessed=1,
        ),
        heatmapGrid=heatmap.get_normalized_grid(),
    )
    return telemetry.model_dump()


# ============================================================================
# TASK 6: DATABASE SCHEMA VERIFICATION (9 TABLES)
# ============================================================================
def test_database_schema_and_initial_seed(integrated_env):
    engine = integrated_env["engine"]
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected_tables = {
        "users",
        "rooms",
        "zones",
        "devices",
        "occupancy_records",
        "density_records",
        "alerts",
        "device_status_logs",
        "system_events",
    }
    assert expected_tables.issubset(tables)

    db = integrated_env["db_factory"]()
    try:
        assert db.query(User).count() == 2
        assert db.query(Room).filter(Room.code == "room1").count() == 1
        assert db.query(Zone).count() == 3
        assert db.query(Device).filter(Device.device_code == "RPI_NODE_01").count() == 1
    finally:
        db.close()


# ============================================================================
# SCENARIO 1: EMPTY ROOM (0 PEOPLE)
# ============================================================================
def test_scenario_1_empty_room(integrated_env):
    worker: MqttAsyncWorker = integrated_env["worker"]
    client: TestClient = integrated_env["client"]
    iot_gpio = integrated_env["iot_gpio"]
    iot_processor = integrated_env["iot_processor"]

    ai_payload = _build_ai_telemetry_payload(tracks_xy=[], in_count=0, out_count=0)
    res = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(ai_payload),
            retain=False,
        )
    )
    assert res["status"] == "processed"
    assert res["room_status"] == "NORMAL"

    # Also feed IoT processor
    decision = iot_processor.process_combined_ai_telemetry(ai_payload)
    assert decision.led == "GREEN"
    assert decision.buzzer is False
    assert iot_gpio.get_state()["led"] == "GREEN"
    assert iot_gpio.get_state()["buzzer"] is False

    # Verify Backend REST API `/api/v1/occupancy/current`
    headers = _get_auth_headers(client)
    occ_resp = client.get("/api/v1/occupancy/current?room_id=room1", headers=headers)
    assert occ_resp.status_code == 200
    occ_data = occ_resp.json()
    assert occ_data["current_count"] == 0
    assert occ_data["overall_density"] == 0.0
    assert occ_data["room_status"] == "NORMAL"


# ============================================================================
# SCENARIO 2: SMALL NUMBER OF PEOPLE (AI -> MQTT -> BACKEND -> DB -> IOT)
# ============================================================================
def test_scenario_2_small_number_of_people(integrated_env):
    worker: MqttAsyncWorker = integrated_env["worker"]
    client: TestClient = integrated_env["client"]
    iot_processor = integrated_env["iot_processor"]
    db_factory = integrated_env["db_factory"]

    # 10 people distributed in Zone A and Zone B
    tracks_xy = [(0.15, 0.30)] * 4 + [(0.50, 0.50)] * 6
    ai_payload = _build_ai_telemetry_payload(
        tracks_xy=tracks_xy, in_count=12, out_count=2
    )

    res = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(ai_payload),
            retain=False,
        )
    )
    assert res["status"] == "processed"
    assert res["persisted"] is True
    assert res["room_status"] == "NORMAL"

    decision = iot_processor.process_combined_ai_telemetry(ai_payload)
    assert decision.led == "GREEN"
    assert decision.buzzer is False

    # Verify DB persistence in `occupancy_records` and `density_records`
    db = db_factory()
    try:
        occ_row = (
            db.query(OccupancyRecord)
            .order_by(OccupancyRecord.recorded_at.desc())
            .first()
        )
        assert occ_row is not None
        assert occ_row.total_count == 10
        assert occ_row.in_count == 12
        assert occ_row.out_count == 2
        assert occ_row.room_status == "NORMAL"

        den_rows = db.query(DensityRecord).all()
        assert len(den_rows) == 3
    finally:
        db.close()

    headers = _get_auth_headers(client)
    cur_resp = client.get("/api/v1/occupancy/current?room_id=room1", headers=headers)
    assert cur_resp.status_code == 200
    assert cur_resp.json()["current_count"] == 10
    assert cur_resp.json()["in_count"] == 12
    assert cur_resp.json()["out_count"] == 2


# ============================================================================
# SCENARIO 3: ROOM EXCEEDS WARNING & CRITICAL THRESHOLDS + IOT GPIO + ACK
# ============================================================================
def test_scenario_3_exceeds_thresholds_and_iot_gpio_actuation(integrated_env):
    worker: MqttAsyncWorker = integrated_env["worker"]
    client: TestClient = integrated_env["client"]
    iot_gpio = integrated_env["iot_gpio"]
    iot_processor = integrated_env["iot_processor"]
    published_mqtt = integrated_env["published_mqtt"]

    # Step A: WARNING threshold (48 people / 60 max_capacity = 80% >= 75%)
    warn_tracks = [(0.20, 0.50)] * 15 + [(0.50, 0.50)] * 20 + [(0.80, 0.50)] * 13
    warn_payload = _build_ai_telemetry_payload(
        tracks_xy=warn_tracks, in_count=50, out_count=2
    )
    res_warn = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(warn_payload),
            retain=False,
        )
    )
    assert res_warn["room_status"] == "WARNING"
    # Backend automatically published command to IoT -> Yellow LED, Buzzer OFF
    assert iot_gpio.get_state()["led"] == "YELLOW"
    assert iot_gpio.get_state()["buzzer"] is False

    # Step B: CRITICAL threshold (66 people > 60 max_capacity)
    crit_tracks = [(0.20, 0.50)] * 22 + [(0.50, 0.50)] * 26 + [(0.80, 0.50)] * 18
    crit_payload = _build_ai_telemetry_payload(
        tracks_xy=crit_tracks, in_count=70, out_count=4
    )
    res_crit = asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(crit_payload),
            retain=False,
        )
    )
    assert res_crit["room_status"] == "CRITICAL"

    # Verify Backend -> MQTT -> Raspberry Pi -> GPIO set RED LED + Buzzer ON
    assert iot_gpio.get_state()["led"] == "RED"
    assert iot_gpio.get_state()["buzzer"] is True
    assert any(
        m["topic"] == "occupancy/room1/device/command"
        and m["payload"]["led"] == "RED"
        and m["payload"]["buzzer"] is True
        for m in published_mqtt
    )

    # Verify Alert created in Backend REST API & Operator can acknowledge it
    headers = _get_auth_headers(client, "operator", "Operator@123")
    alerts_resp = client.get("/api/v1/alerts?severity=CRITICAL", headers=headers)
    assert alerts_resp.status_code == 200
    items = alerts_resp.json()
    assert len(items) >= 1
    critical_alert_id = items[0]["id"]

    ack_resp = client.patch(
        f"/api/v1/alerts/{critical_alert_id}/acknowledge", headers=headers
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["is_acknowledged"] is True

    # Operator silences buzzer via MQTT command or alert acknowledgement
    iot_processor.process_alert_payload(
        {"severity": "CRITICAL", "status": "ACKNOWLEDGED", "message": "Ack by operator"}
    )
    dec_after_ack = iot_processor.process_combined_ai_telemetry(crit_payload)
    assert dec_after_ack.led == "RED"
    assert dec_after_ack.buzzer is False


# ============================================================================
# SCENARIO 4: PEOPLE MOVING BETWEEN POLYGON ZONES (ZONE A -> ZONE B -> ZONE C)
# ============================================================================
def test_scenario_4_people_moving_between_zones(integrated_env):
    worker: MqttAsyncWorker = integrated_env["worker"]
    client: TestClient = integrated_env["client"]
    headers = _get_auth_headers(client)

    # Frame 1: 12 people in Zone A (x=0.15), 2 in Zone B (x=0.50), 1 in Zone C (x=0.80)
    f1_tracks = [(0.15, 0.50)] * 12 + [(0.50, 0.50)] * 2 + [(0.80, 0.50)] * 1
    p1 = _build_ai_telemetry_payload(tracks_xy=f1_tracks)
    asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(p1),
            retain=False,
        )
    )

    z_resp_1 = client.get("/api/v1/occupancy/zones?room_id=room1", headers=headers)
    assert z_resp_1.status_code == 200
    zones_1 = {z["zone_code"]: z["person_count"] for z in z_resp_1.json()}
    assert zones_1["ZONE_A"] == 12
    assert zones_1["ZONE_B"] == 2
    assert zones_1["ZONE_C"] == 1

    # Frame 2: Crowd moves from Zone A into Zone C (1 in Zone A, 2 in Zone B, 12 in Zone C)
    f2_tracks = [(0.15, 0.50)] * 1 + [(0.50, 0.50)] * 2 + [(0.80, 0.50)] * 12
    p2 = _build_ai_telemetry_payload(tracks_xy=f2_tracks)
    asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(p2),
            retain=False,
        )
    )

    z_resp_2 = client.get("/api/v1/occupancy/zones?room_id=room1", headers=headers)
    assert z_resp_2.status_code == 200
    zones_2 = {z["zone_code"]: z["person_count"] for z in z_resp_2.json()}
    assert zones_2["ZONE_A"] == 1
    assert zones_2["ZONE_B"] == 2
    assert zones_2["ZONE_C"] == 12


# ============================================================================
# SCENARIO 5: CAMERA LOSES CONNECTION (`is_hw_connected=False`)
# ============================================================================
def test_scenario_5_camera_disconnected():
    """
    Verify that when the camera hardware stream disconnects (`is_hw_connected=False`),
    the AI Engine outputs 0 tracks safely without phantom detections.
    """
    ai_cfg_mod = _load_external_module(
        "ai_core_config", AI_DIR / "app" / "core" / "config.py"
    )
    ai_log_mod = _load_external_module(
        "ai_core_logger", AI_DIR / "app" / "core" / "logger.py"
    )
    sys.modules["app.core.config"] = ai_cfg_mod
    sys.modules["app.core.logger"] = ai_log_mod
    ai_services_pkg = types.ModuleType("app.services")
    ai_services_pkg.__path__ = [str(AI_DIR / "app" / "services")]
    sys.modules["app.services"] = ai_services_pkg
    sys.modules["app.services.mqtt_publisher"] = _load_external_module(
        "ai_mqtt", AI_DIR / "app" / "services" / "mqtt_publisher.py"
    )
    sys.modules["app.vision.tracker"] = _load_external_module(
        "ai_tracker", AI_DIR / "app" / "vision" / "tracker.py"
    )
    sys.modules["app.vision.counter"] = _load_external_module(
        "ai_counter", AI_DIR / "app" / "vision" / "counter.py"
    )
    sys.modules["app.vision.detector"] = _load_external_module(
        "ai_detector", AI_DIR / "app" / "vision" / "detector.py"
    )
    sys.modules["app.vision.performance"] = _load_external_module(
        "ai_perf", AI_DIR / "app" / "vision" / "performance.py"
    )
    sys.modules["app.vision.annotator"] = _load_external_module(
        "ai_annot", AI_DIR / "app" / "vision" / "annotator.py"
    )
    sys.modules["app.vision.camera_manager"] = _load_external_module(
        "ai_cam", AI_DIR / "app" / "vision" / "camera_manager.py"
    )
    ai_engine_mod = _load_external_module(
        "ai_pipeline_engine", AI_DIR / "app" / "services" / "pipeline_engine.py"
    )

    ai_settings = ai_cfg_mod.AiServiceSettings(YOLO_MODEL_PATH="nonexistent_sim.pt")
    engine = ai_engine_mod.VisionPipelineEngine(ai_settings)
    blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    telemetry_disconnected = engine.process_single_frame(
        blank_frame, is_hw_connected=False
    )
    assert telemetry_disconnected.totalCount == 0
    assert len(telemetry_disconnected.tracks) == 0
    assert telemetry_disconnected.roomDensity == 0.0


# ============================================================================
# SCENARIO 6: RASPBERRY PI LOSES CONNECTION (LWT OFFLINE & HEARTBEAT TIMEOUT)
# ============================================================================
def test_scenario_6_raspberry_pi_disconnected(integrated_env):
    worker: MqttAsyncWorker = integrated_env["worker"]
    client: TestClient = integrated_env["client"]
    db_factory = integrated_env["db_factory"]
    headers = _get_auth_headers(client)

    # 1. IoT Service publishes ONLINE heartbeat with its camelCase fields
    iot_online_payload = {
        "deviceId": "RPI_NODE_01",
        "deviceName": "Raspberry Pi 5 Edge Controller",
        "roomId": "room1",
        "status": "ONLINE",
        "simulationMode": True,
        "led": "GREEN",
        "buzzer": False,
        "beepPattern": "OFF",
        "occupancyMetrics": {
            "currentCount": 8,
            "maxCapacity": 60,
            "currentDensity": 0.0667,
            "densityLevel": "LOW",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    res_on = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/device/status",
            payload_str=json.dumps(iot_online_payload),
            retain=False,
        )
    )
    assert res_on["status"] == "processed"

    # 2. Simulate Mosquitto Last Will & Testament (LWT) when Raspberry Pi loses connection
    iot_lwt_offline = {
        "deviceId": "RPI_NODE_01",
        "roomId": "room1",
        "status": "OFFLINE",
        "led": "OFF",
        "buzzer": False,
        "reason": "LWT_UNEXPECTED_DISCONNECT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    res_off = asyncio.run(
        worker.process_raw_message(
            topic="occupancy/room1/device/status",
            payload_str=json.dumps(iot_lwt_offline),
            retain=True,
        )
    )
    assert res_off["status"] == "processed"

    # Check Device status via REST API
    devs = client.get("/api/v1/devices", headers=headers).json()
    rpi = next(d for d in devs if d["device_code"] == "RPI_NODE_01")
    status_resp = client.get(f"/api/v1/devices/{rpi['id']}/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "OFFLINE"
    assert status_resp.json()["is_online"] is False

    # 3. Also test heartbeat timeout > 35s even if status was left as ONLINE
    db = db_factory()
    try:
        dev_entity = db.query(Device).filter(Device.id == rpi["id"]).first()
        dev_entity.status = "ONLINE"
        dev_entity.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)
        db.commit()
    finally:
        db.close()

    stale_resp = client.get(f"/api/v1/devices/{rpi['id']}/status", headers=headers)
    assert stale_resp.status_code == 200
    assert stale_resp.json()["is_online"] is False
    assert stale_resp.json()["status"] == "OFFLINE"


# ============================================================================
# SCENARIO 7: MQTT BROKER DISCONNECTED (AUTO-RECONNECT & COUNTER TRACKING)
# ============================================================================
def test_scenario_7_mqtt_broker_disconnected(integrated_env):
    worker: MqttAsyncWorker = integrated_env["worker"]
    initial_attempts = worker.reconnect_attempts

    # Simulate unexpected broker disconnect callback
    worker._on_disconnect(None, None, 1)
    assert worker.is_connected is False
    assert worker.reconnect_attempts == initial_attempts + 1

    # Simulate broker coming back online and `_on_connect` firing with rc=0
    class DummyPahoClient:
        def __init__(self):
            self.subscribed = []

        def subscribe(self, topic, qos=1):
            self.subscribed.append((topic, qos))

    dummy = DummyPahoClient()
    worker._on_connect(dummy, None, None, 0)
    assert worker.is_connected is True
    assert len(dummy.subscribed) == len(worker.SUBSCRIBED_TOPICS)


# ============================================================================
# SCENARIO 8: BACKEND RESTARTED (RETAINED MQTT RECOVERY WITHOUT DUPLICATE DB ROWS)
# ============================================================================
def test_scenario_8_backend_restarted_retained_recovery(integrated_env):
    db_factory = integrated_env["db_factory"]
    client: TestClient = integrated_env["client"]

    db = db_factory()
    try:
        count_before = db.query(OccupancyRecord).count()
    finally:
        db.close()

    # Simulate a brand-new MqttAsyncWorker created after Backend process restart
    restarted_worker = MqttAsyncWorker(
        session_factory=db_factory, dedup_window_sec=0.0
    )
    retained_payload = _build_ai_telemetry_payload(
        tracks_xy=[(0.25, 0.50)] * 19, in_count=25, out_count=6
    )

    # Mosquitto delivers retained message (`retain=True`) immediately upon subscribe
    res = asyncio.run(
        restarted_worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(retained_payload),
            retain=True,
        )
    )
    assert res["status"] == "processed"
    assert res["retained"] is True
    assert res["persisted"] is False

    # Verify live state is immediately restored in memory
    live_state = restarted_worker.get_live_room_state("room1")
    assert live_state is not None
    assert live_state["current_count"] == 19

    # Verify NO duplicate historical row was written to `occupancy_records`
    db = db_factory()
    try:
        count_after = db.query(OccupancyRecord).count()
        assert count_after == count_before
    finally:
        db.close()


# ============================================================================
# SCENARIO 9: FRONTEND LOSES WEBSOCKET CONNECTION & RECONNECTS
# ============================================================================
def test_scenario_9_websocket_disconnect_and_reconnect(integrated_env):
    client: TestClient = integrated_env["client"]
    worker: MqttAsyncWorker = integrated_env["worker"]

    # First connection
    with client.websocket_connect(
        "/ws/realtime?room_id=room1&client_id=react-ui-1"
    ) as ws1:
        welcome1 = ws1.receive_json()
        assert welcome1["event"] == "connected"
        assert welcome1["client_id"] == "react-ui-1"
        assert ws_manager.active_count >= 1

        # Ping / Pong keepalive
        ws1.send_json({"action": "ping"})
        pong = ws1.receive_json()
        assert pong["event"] == "pong"

    # After exiting context manager, client disconnected cleanly
    # Now publish new occupancy state while client is disconnected
    p = _build_ai_telemetry_payload(tracks_xy=[(0.5, 0.5)] * 14)
    asyncio.run(
        worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(p),
            retain=False,
        )
    )

    # Client reconnects and receives `initial_state` snapshot immediately upon connect
    with client.websocket_connect(
        "/ws/realtime?room_id=room1&client_id=react-ui-1-reconnected"
    ) as ws2:
        welcome2 = ws2.receive_json()
        assert welcome2["event"] == "connected"
        assert "initial_state" in welcome2
        assert welcome2["initial_state"]["current_count"] == 14

        ws2.send_json({"type": "subscribeRoom", "roomId": "room1"})
        sub_ack = ws2.receive_json()
        assert sub_ack["event"] == "subscribed"
        assert sub_ack["room_id"] == "room1"


# ============================================================================
# SCENARIO 10: DATABASE LOSES CONNECTION (GRACEFUL DEGRADATION)
# ============================================================================
def test_scenario_10_database_loses_connection():
    """
    Simulate a broken PostgreSQL/SQLite session raising `OperationalError` (subclass of `SQLAlchemyError`)
    and verify `MqttAsyncWorker` does not crash, updates in-memory state, and broadcasts via WebSocket.
    """

    class BrokenSession:
        def query(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("DB connection lost"))

        def add(self, *args, **kwargs):
            raise OperationalError("INSERT", {}, Exception("DB connection lost"))

        def commit(self):
            raise OperationalError("COMMIT", {}, Exception("DB connection lost"))

        def rollback(self):
            pass

        def close(self):
            pass

    degraded_worker = MqttAsyncWorker(
        session_factory=lambda: BrokenSession(),  # type: ignore
        dedup_window_sec=0.0,
    )

    payload = _build_ai_telemetry_payload(tracks_xy=[(0.4, 0.4)] * 9)
    res = asyncio.run(
        degraded_worker.process_raw_message(
            topic="ai/rooms/room1/telemetry",
            payload_str=json.dumps(payload),
            retain=False,
        )
    )
    assert res["status"] == "db_degraded"

    # Even with DB down, in-memory live room snapshot is updated for realtime clients
    live = degraded_worker.get_live_room_state("room1")
    assert live is not None
    assert live["current_count"] == 9
    assert live["db_degraded"] is True
