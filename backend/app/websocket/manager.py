"""
Realtime WebSocket Connection Manager.
Supports:
- Multiple concurrent WebSocket clients with optional room filtering
- Automatic removal of dead/disconnected clients
- Strict error isolation so one faulty client cannot disrupt others
- Heartbeat (`ping` / `pong`) protocol
- Standard event envelopes:
  - `occupancy.updated`
  - `density.updated`
  - `zone.updated`
  - `alert.created`
  - `device.status_changed`
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
        self.connected_at: datetime = datetime.now(timezone.utc)
        self.last_pong_at: datetime = datetime.now(timezone.utc)


class WebSocketManager:
    """Thread-safe / async-safe manager for broadcasting realtime events."""

    def __init__(self) -> None:
        self._clients: Dict[str, ClientConnection] = {}
        self._lock = asyncio.Lock()

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

    async def handle_client_message(
        self, client_id: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process incoming client control frames (`ping`, `subscribeRoom`)."""
        msg_type = str(
            message.get("type")
            or message.get("event")
            or message.get("action")
            or ""
        ).lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        if msg_type == "ping":
            async with self._lock:
                conn = self._clients.get(client_id)
                if conn:
                    conn.last_pong_at = datetime.now(timezone.utc)
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

        return None

    async def send_to_client(
        self, client_id: str, payload: Dict[str, Any]
    ) -> bool:
        """Send JSON message to a single client with error isolation."""
        conn = self._clients.get(client_id)
        if conn is None:
            return False
        try:
            await conn.websocket.send_json(payload)
            return True
        except Exception as exc:
            logger.warning(
                "Removing broken WebSocket client %s on send error: %s",
                client_id,
                exc,
            )
            await self.disconnect(client_id)
            return False

    async def broadcast_event(
        self,
        event: str,
        data: Dict[str, Any],
        room_id: Optional[str] = None,
    ) -> int:
        """
        Broadcast a typed realtime event to all matching clients.
        Dead or broken connections are isolated and cleaned up automatically.
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

        delivered = 0
        stale_client_ids: List[str] = []

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

        for conn in snapshot:
            if (
                candidate_rooms
                and conn.subscribed_rooms
                and not (candidate_rooms & conn.subscribed_rooms)
            ):
                continue
            try:
                await conn.websocket.send_json(envelope)
                delivered += 1
            except Exception as exc:
                logger.warning(
                    "Isolated WebSocket send failure for client %s: %s",
                    conn.client_id,
                    exc,
                )
                stale_client_ids.append(conn.client_id)

        for dead_id in stale_client_ids:
            await self.disconnect(dead_id)

        return delivered


ws_manager = WebSocketManager()
