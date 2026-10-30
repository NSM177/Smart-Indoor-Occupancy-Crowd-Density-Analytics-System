"""
MQTT Publisher & Config Subscriber for the AI Vision Service.
Publishes real-time occupancy and zone density telemetry to `ai/rooms/{roomId}/telemetry`
and listens for live polygon zone & camera updates on `ai/rooms/+/config`.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from app.core.config import AiServiceSettings
from app.core.logger import get_logger

logger = get_logger("ai.mqtt_publisher")


class AiMqttBridge:
    """Manages MQTT pub/sub between AI Vision Service and Mosquitto Broker."""

    def __init__(
        self,
        settings: AiServiceSettings,
        on_config_update: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.settings = settings
        self.on_config_update = on_config_update

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="ai_vision_service_node",
            clean_session=True,
        )
        if settings.MQTT_USERNAME:
            self.client.username_pw_set(
                settings.MQTT_USERNAME, settings.MQTT_PASSWORD
            )

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        logger.info(
            "Connecting AI Vision Service to MQTT Broker %s:%d...",
            self.settings.MQTT_HOST,
            self.settings.MQTT_PORT,
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=15)
        try:
            self.client.connect_async(
                self.settings.MQTT_HOST,
                self.settings.MQTT_PORT,
                keepalive=30,
            )
            self.client.loop_start()
        except Exception as exc:
            logger.warning("MQTT initial connect_async warning: %s", exc)

    def stop(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return bool(self.client.is_connected())

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        logger.info(
            "AI Service connected to MQTT Broker (reason_code=%s). Subscribing to ai/rooms/+/config",
            reason_code,
        )
        client.subscribe("ai/rooms/+/config", qos=1)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        logger.warning(
            "AI Service disconnected from MQTT Broker (reason_code=%s)",
            reason_code,
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if self.on_config_update and isinstance(payload, dict):
                self.on_config_update(payload)
        except Exception as exc:
            logger.warning(
                "Failed to parse config message on %s: %s", msg.topic, exc
            )

    def publish_telemetry(
        self, room_id: str, payload: Dict[str, Any]
    ) -> bool:
        if not self.client.is_connected() or not room_id:
            return False
        topic = f"ai/rooms/{room_id}/telemetry"
        try:
            self.client.publish(
                topic,
                json.dumps(payload),
                qos=0,
                retain=False,
            )

            # Also publish granular topics for Raspberry Pi IoT Edge subscribers
            for target_room in {room_id, "room1"}:
                self.client.publish(
                    f"occupancy/{target_room}/count",
                    json.dumps(
                        {
                            "roomId": target_room,
                            "totalCount": payload.get("totalCount", 0),
                            "maxCapacity": payload.get("roomMaxCapacity", 60),
                            "occupancyRate": payload.get("roomOccupancyRate", 0.0),
                            "timestamp": payload.get("timestamp"),
                        }
                    ),
                    qos=0,
                )
                self.client.publish(
                    f"occupancy/{target_room}/density",
                    json.dumps(
                        {
                            "roomId": target_room,
                            "roomDensity": payload.get("roomDensity", 0.0),
                            "densityLevel": payload.get("roomDensityLevel", "LOW"),
                            "zones": payload.get("zones", []),
                            "timestamp": payload.get("timestamp"),
                        }
                    ),
                    qos=0,
                )
                active_alerts = payload.get("activeAlerts") or []
                if active_alerts:
                    top_alert = active_alerts[0]
                    self.client.publish(
                        f"occupancy/{target_room}/alerts",
                        json.dumps(
                            {
                                "roomId": target_room,
                                "severity": top_alert.get("severity", "WARNING"),
                                "status": "ACTIVE",
                                "message": top_alert.get("message", ""),
                                "timestamp": payload.get("timestamp"),
                            }
                        ),
                        qos=1,
                    )
            return True
        except Exception as exc:
            logger.debug("MQTT telemetry publish error: %s", exc)
            return False
