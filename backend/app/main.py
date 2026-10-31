"""
Main FastAPI Application Entrypoint for:
Smart Indoor Occupancy & Crowd Density Analytics System (Python Backend).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import uvicorn

from app.api.v1.alerts.router import router as alerts_router
from app.api.v1.analytics.router import router as analytics_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.devices.router import router as devices_router
from app.api.v1.occupancy.router import router as occupancy_router
from app.api.v1.rooms.router import router as rooms_router
from app.api.v1.zones.router import router as zones_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.database.base import Base
from app.database.seed import seed_initial_data
from app.database.session import SessionLocal, engine
from app.mqtt.worker import mqtt_worker
from app.websocket.manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database schema, seed initial entities, and start async MQTT worker."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()

    await mqtt_worker.start()
    logger.info("%s started on port %d", settings.APP_NAME, settings.BACKEND_PORT)
    try:
        yield
    finally:
        await mqtt_worker.stop()
        logger.info("%s shut down cleanly.", settings.APP_NAME)


def create_app(
    enable_lifespan_db: bool = True,
    enable_mqtt_broker: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def app_lifespan(app: FastAPI):
        if enable_lifespan_db:
            Base.metadata.create_all(bind=engine)
            db = SessionLocal()
            try:
                seed_initial_data(db)
            finally:
                db.close()

        if enable_mqtt_broker:
            await mqtt_worker.start()
        ws_manager.start_liveness_monitor()
        logger.info("%s started on port %d", settings.APP_NAME, settings.BACKEND_PORT)
        try:
            yield
        finally:
            await ws_manager.stop_liveness_monitor()
            if enable_mqtt_broker:
                await mqtt_worker.stop()
            logger.info("%s shut down cleanly.", settings.APP_NAME)

    app = FastAPI(
        title=settings.APP_NAME,
        version="2.0.0",
        description=(
            "Modular Python FastAPI Backend for Smart Indoor Occupancy & "
            "Crowd Density Analytics System (PostgreSQL, SQLAlchemy 2.0, "
            "Alembic, Paho-MQTT, WebSocket, JWT RBAC)."
        ),
        lifespan=app_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    api_prefix = "/api/v1"
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(rooms_router, prefix=api_prefix)
    app.include_router(zones_router, prefix=api_prefix)
    app.include_router(occupancy_router, prefix=api_prefix)
    app.include_router(alerts_router, prefix=api_prefix)
    app.include_router(devices_router, prefix=api_prefix)
    app.include_router(analytics_router, prefix=api_prefix)

    @app.get("/health", tags=["Health"])
    @app.get("/api/v1/health", tags=["Health"])
    def health_check() -> Dict[str, Any]:
        db_ok = False
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        finally:
            db.close()

        return {
            "status": "ok" if db_ok else "degraded",
            "service": "smart-occupancy-python-backend",
            "version": "2.0.0",
            "database_connected": db_ok,
            "mqtt_connected": mqtt_worker.is_connected,
            "active_ws_clients": ws_manager.active_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _send_latest_heatmaps(cid: str) -> None:
        """Give a client that just opted into heatmaps the current grid right away."""
        conn = ws_manager.get_client(cid)
        if conn is None:
            return
        sent = set()
        for room_key in conn.subscribed_rooms:
            heatmap = mqtt_worker.get_live_heatmap(room_key)
            if heatmap and heatmap["room_id"] not in sent:
                sent.add(heatmap["room_id"])
                await ws_manager.send_to_client(
                    cid,
                    {
                        "event": "heatmap.updated",
                        "room_id": heatmap["room_id"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": heatmap,
                    },
                )

    @app.websocket("/ws/realtime")
    @app.websocket("/api/v1/ws")
    async def websocket_realtime_endpoint(
        websocket: WebSocket,
        room_id: Optional[str] = Query(default=None),
        client_id: Optional[str] = Query(default=None),
    ) -> None:
        cid = client_id or f"ws_{uuid.uuid4().hex[:10]}"
        await ws_manager.connect(websocket, client_id=cid, room_id=room_id)
        try:
            # Send initial connection acknowledgement & latest snapshot if available
            welcome: Dict[str, Any] = {
                "event": "connected",
                "client_id": cid,
                "room_id": room_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if room_id:
                live = mqtt_worker.get_live_room_state(room_id)
                if live:
                    welcome["initial_state"] = live
            await ws_manager.send_to_client(cid, welcome)

            while True:
                msg = await websocket.receive_json()
                if isinstance(msg, dict):
                    ack = await ws_manager.handle_client_message(cid, msg)
                    if ack and ack.get("event") == "heatmap_subscription" and ack["enabled"]:
                        await _send_latest_heatmaps(cid)
        except WebSocketDisconnect:
            await ws_manager.disconnect(cid)
        except Exception as exc:
            logger.debug("WebSocket session %s closed: %s", cid, exc)
            await ws_manager.disconnect(cid)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=False,
    )
