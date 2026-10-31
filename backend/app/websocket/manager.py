"""
Realtime WebSocket Connection Manager.
Supports:
- Multiple concurrent WebSocket clients with optional room filtering
- Automatic removal of dead/disconnected clients
- Strict error isolation so one faulty client cannot disrupt others
- Concurrent, time-bounded fan-out so one slow client cannot stall the others
- Heartbeat (`ping` / `pong`) protocol and idle-client eviction
- Opt-in `heatmap.updated` stream (`{"type": "subscribeHeatmap", "enabled": true}`)
- Standard event envelopes:
  - `occupancy.updated`
  - `density.updated`
  - `zone.updated`
  - `heatmap.updated`
  - `alert.created`
  - `device.status_changed`
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("backend.websocket")


class ClientConnection:
    """Represents a connected WebSocket client and its subscribed rooms."""

    def __init__(self, websocket: WebSocket, client_id: str) -> None:
        self.websocket = websocket
        self.client_id = client_id
        self.subscribed_rooms: Set[str] = set()  # empty set = subscribed to all rooms
        self.wants_heatmap: bool = False
        self.connected_at: datetime = datetime.now(timezone.utc)
        self.last_pong_at: datetime = datetime.now(timezone.utc)


class WebSocketManager:
    """Thread-safe / async-safe manager for broadcasting realtime events."""

    # A send that takes longer than this marks the client as stalled
    SEND_TIMEOUT_SEC: float = 2.0
    # Clients ping every 20s; evict those silent for longer than this
    IDLE_TIMEOUT_SEC: float = 75.0
    SWEEP_INTERVAL_SEC: float = 30.0

    def __init__(self) -> None:
        self._clients: Dict[str, ClientConnection] = {}
        self._lock = asyncio.Lock()
        self._sweeper_task: Optional[asyncio.Task] = None

    @property
    def active_count(self) -> int:
        return len(self._clients)

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        room_id: Optional[str] = None,
    ) -> ClientConnection:
        await websocket.accept()
        conn = ClientConnection(websocket=websocket, client_id=client_id)
        if room_id:
            conn.subscribed_rooms.add(room_id)
        async with self._lock:
            self._clients[client_id] = conn
        logger.info(
            "WebSocket client connected: %s (active=%d)",
            client_id,
            len(self._clients),
        )
        return conn

    async def disconnect(self, client_id: str) -> None:
        async with self._lock:
            removed = self._clients.pop(client_id, None)
        if removed is not None:
            logger.info(
                "WebSocket client disconnected: %s (active=%d)",
                client_id,
                len(self._clients),
            )

    async def subscribe_room(self, client_id: str, room_id: str) -> None:
        async with self._lock:
            conn = self._clients.get(client_id)
            if conn:
                conn.subscribed_rooms.add(room_id)

    def get_client(self, client_id: str) -> Optional[ClientConnection]:
        return self._clients.get(client_id)

    async def handle_client_message(
        self, client_id: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process incoming client control frames (`ping`, `subscribeRoom`, `subscribeHeatmap`)."""
        msg_type = str(
            message.get("type")
            or message.get("event")
            or message.get("action")
            or ""
        ).lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Any frame from the client proves the connection is alive
        conn = self._clients.get(client_id)
        if conn:
            conn.last_pong_at = datetime.now(timezone.utc)

        if msg_type == "ping":
            response = {"event": "pong", "type": "pong", "timestamp": now_iso}
            await self.send_to_client(client_id, response)
            return response

        if msg_type in ("subscriberoom", "subscribe_room", "subscribe"):
            room_id = message.get("roomId") or message.get("room_id")
            if room_id:
                await self.subscribe_room(client_id, str(room_id))
            ack = {
                "event": "subscribed",
                "room_id": room_id,
                "timestamp": now_iso,
            }
            await self.send_to_client(client_id, ack)
            return ack

        if msg_type in ("subscribeheatmap", "subscribe_heatmap"):
            enabled = bool(message.get("enabled", True))
            if conn:
                conn.wants_heatmap = enabled
            ack = {
                "event": "heatmap_subscription",
                "enabled": enabled,
                "timestamp": now_iso,
            }
            await self.send_to_client(client_id, ack)
            return ack

        return None

    async def send_to_client(
        self, client_id: str, payload: Dict[str, Any]
    ) -> bool:
        """Send JSON message to a single client with error isolation."""
        conn = self._clients.get(client_id)
        if conn is None:
            return False
        if await self._send_text(conn, self._encode(payload)):
            return True
        await self._drop_client(conn)
        return False

    async def broadcast_event(
        self,
        event: str,
        data: Dict[str, Any],
        room_id: Optional[str] = None,
        heatmap_only: bool = False,
    ) -> int:
        """
        Broadcast a typed realtime event to all matching clients.
        The envelope is serialized once and sent to all clients concurrently, each
        send bounded by `SEND_TIMEOUT_SEC`. Dead, broken or stalled connections are
        isolated and cleaned up automatically.
        Returns the number of clients that successfully received the message.
        """
        envelope = {
            "event": event,
            "room_id": room_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        async with self._lock:
            snapshot: List[ClientConnection] = list(self._clients.values())

        candidate_rooms = {
            str(r)
            for r in (
                room_id,
                data.get("room_id") if isinstance(data, dict) else None,
                data.get("room_code") if isinstance(data, dict) else None,
                data.get("roomId") if isinstance(data, dict) else None,
            )
            if r
        }

        targets = [
            conn
            for conn in snapshot
            if not (heatmap_only and not conn.wants_heatmap)
            and not (
                candidate_rooms
                and conn.subscribed_rooms
                and not (candidate_rooms & conn.subscribed_rooms)
            )
        ]
        if not targets:
            return 0

        text = self._encode(envelope)
        results = await asyncio.gather(
            *(self._send_text(conn, text) for conn in targets)
        )

        delivered = 0
        for conn, ok in zip(targets, results):
            if ok:
                delivered += 1
            else:
                await self._drop_client(conn)
        return delivered

    def start_liveness_monitor(self) -> None:
        """Start the periodic sweep that evicts clients which stopped pinging."""
        if self._sweeper_task is None or self._sweeper_task.done():
            self._sweeper_task = asyncio.create_task(
                self._sweep_idle_clients_loop(), name="ws-liveness-sweeper"
            )

    async def stop_liveness_monitor(self) -> None:
        if self._sweeper_task is not None:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
            self._sweeper_task = None

    async def evict_idle_clients(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._lock:
            idle = [
                conn
                for conn in self._clients.values()
                if (now - conn.last_pong_at).total_seconds() > self.IDLE_TIMEOUT_SEC
            ]
        for conn in idle:
            logger.info("Evicting idle WebSocket client %s", conn.client_id)
            await self._drop_client(conn)
        return len(idle)

    async def _sweep_idle_clients_loop(self) -> None:
        while True:
            await asyncio.sleep(self.SWEEP_INTERVAL_SEC)
            try:
                await self.evict_idle_clients()
            except Exception as exc:
                logger.warning("WebSocket liveness sweep failed: %s", exc)

    @staticmethod
    def _encode(payload: Dict[str, Any]) -> str:
        # Same encoding Starlette's `send_json` uses
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    async def _send_text(self, conn: ClientConnection, text: str) -> bool:
        try:
            await asyncio.wait_for(
                conn.websocket.send_text(text), timeout=self.SEND_TIMEOUT_SEC
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket client %s stalled for >%.1fs; dropping it",
                conn.client_id,
                self.SEND_TIMEOUT_SEC,
            )
            return False
        except Exception as exc:
            logger.warning(
                "Isolated WebSocket send failure for client %s: %s",
                conn.client_id,
                exc,
            )
            return False

    async def _drop_client(self, conn: ClientConnection) -> None:
        await self.disconnect(conn.client_id)
        close = getattr(conn.websocket, "close", None)
        if close is None:
            return
        try:
            await asyncio.wait_for(close(), timeout=1.0)
        except Exception:
            pass


ws_manager = WebSocketManager()
