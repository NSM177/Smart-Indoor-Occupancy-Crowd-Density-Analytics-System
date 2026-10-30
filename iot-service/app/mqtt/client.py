"""
Layer 3: MQTT Communication Layer (`client.py`).
Connects the Raspberry Pi Edge Node to Eclipse Mosquitto with:
- Automatic Reconnect (Exponential Backoff: 1s .. 30s)
- Last Will & Testament (LWT) on `occupancy/{roomId}/device/status` and `iot/devices/{deviceId}/status`
- Subscriptions to:
  * `occupancy/{roomId}/count`
  * `occupancy/{roomId}/density`
  * `occupancy/{roomId}/alerts`
  * `occupancy/{roomId}/device/command`
  * `ai/rooms/+/telemetry`
  * `iot/devices/{deviceId}/command`
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import threading
import time
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from app.config import IotSettings
from app.hardware.gpio_driver import GpioController
from app.logger import get_iot_logger
from app.processor.occupancy_processor import OccupancyDataProcessor

logger = get_iot_logger("iot.mqtt.client")


class IotMqttAgent:
    """Manages MQTT pub/sub, auto-reconnect, Last Will, and heartbeat publishing."""

    def __init__(
        self,
        settings: IotSettings,
        gpio_controller: GpioController,
        processor: Optional[OccupancyDataProcessor] = None,
    ) -> None:
        self.settings = settings
        self.gpio = gpio_controller
        self.processor = processor or OccupancyDataProcessor(
            settings=settings, gpio=gpio_controller
        )

        self.device_id = settings.IOT_DEVICE_ID
        self.room_id = settings.IOT_ROOM_ID or "room1"
        self.started_at_mono = time.monotonic()

        # Primary MQTT topics requested in specification
        self.topic_count = f"occupancy/{self.room_id}/count"
        self.topic_density = f"occupancy/{self.room_id}/density"
        self.topic_alerts = f"occupancy/{self.room_id}/alerts"
        self.topic_device_status = f"occupancy/{self.room_id}/device/status"
        self.topic_device_command = f"occupancy/{self.room_id}/device/command"

        # System-wide topics for NestJS Backend & AI Service interoperability
        self.topic_legacy_status = f"iot/devices/{self.device_id}/status"
        self.topic_legacy_command = f"iot/devices/{self.device_id}/command"

        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self.reconnect_attempts: int = 0

        # Publish status immediately whenever GPIO state transitions
        self.gpio.on_state_change = self._on_gpio_state_changed

        client_id = f"iot_edge_{self.device_id}_{int(time.time()) % 10000}"
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=True,
        )

        if settings.MQTT_USERNAME:
            self.client.username_pw_set(
                settings.MQTT_USERNAME, settings.MQTT_PASSWORD
            )

        # Configure MQTT Last Will & Testament (LWT)
        lwt_payload = json.dumps(
            {
                "deviceId": self.device_id,
                "deviceName": self.settings.IOT_DEVICE_NAME,
                "roomId": self.room_id,
                "status": "OFFLINE",
                "simulationMode": self.gpio.is_simulation,
                "gpioConfig": self.gpio.get_gpio_config(),
                "gpioState": {
                    "led": "OFF",
                    "buzzer": False,
                    "beepPattern": "OFF",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.client.will_set(
            self.topic_device_status, payload=lwt_payload, qos=1, retain=True
        )

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        """Connect to Mosquitto broker with automatic exponential backoff reconnect."""
        logger.info(
            "Starting IoT MQTT Agent '%s' (room='%s') -> Broker %s:%d",
            self.device_id,
            self.room_id,
            self.settings.MQTT_HOST,
            self.settings.MQTT_PORT,
        )
        self.client.reconnect_delay_set(
            min_delay=max(1, self.settings.MQTT_RECONNECT_MIN_SEC),
            max_delay=max(5, self.settings.MQTT_RECONNECT_MAX_SEC),
        )
        try:
            self.client.connect_async(
                self.settings.MQTT_HOST,
                self.settings.MQTT_PORT,
                keepalive=self.settings.MQTT_KEEPALIVE_SEC,
            )
            self.client.loop_start()
        except Exception as exc:
            logger.warning("Initial MQTT connect_async warning: %s", exc)

        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="IotHeartbeatThread",
        )
        self._heartbeat_thread.start()

    def stop(self) -> None:
        """Publish graceful OFFLINE status, stop MQTT loop and release GPIO."""
        self._stop_event.set()
        try:
            if self.client.is_connected():
                offline_payload = json.dumps(
                    self._build_status_payload(status="OFFLINE")
                )
                self.client.publish(
                    self.topic_device_status,
                    offline_payload,
                    qos=1,
                    retain=True,
                )
                self.client.publish(
                    self.topic_legacy_status,
                    offline_payload,
                    qos=1,
                    retain=True,
                )
        except Exception:
            pass

        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

        self.gpio.cleanup()

    def check_and_recover_connection(self) -> bool:
        """Invoked by Watchdog to verify MQTT connectivity and force reconnect if needed."""
        if self.client.is_connected():
            return True

        self.reconnect_attempts += 1
        logger.warning(
            "MQTT connection currently down (attempt #%d). Triggering reconnect...",
            self.reconnect_attempts,
        )
        try:
            self.client.reconnect()
            return True
        except Exception:
            try:
                self.client.connect_async(
                    self.settings.MQTT_HOST,
                    self.settings.MQTT_PORT,
                    keepalive=self.settings.MQTT_KEEPALIVE_SEC,
                )
            except Exception as inner_exc:
                logger.debug("Reconnect attempt deferred: %s", inner_exc)
            return False

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        self.reconnect_attempts = 0
        subscriptions = [
            (self.topic_count, 1),
            (self.topic_density, 1),
            (self.topic_alerts, 1),
            (self.topic_device_command, 1),
            ("occupancy/+/count", 1),
            ("occupancy/+/density", 1),
            ("occupancy/+/alerts", 1),
            (self.topic_legacy_command, 1),
            ("ai/rooms/+/telemetry", 0),
        ]
        client.subscribe(subscriptions)
        logger.info(
            "Connected to MQTT Broker (reason=%s). Subscribed to: %s, %s, %s, %s",
            reason_code,
            self.topic_count,
            self.topic_density,
            self.topic_alerts,
            self.topic_device_command,
        )
        self.publish_status()

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        logger.warning(
            "Disconnected from MQTT Broker (reason=%s). Auto-reconnect backoff active.",
            reason_code,
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        self.route_topic_message(msg.topic, msg.payload.decode("utf-8"))

    def route_topic_message(self, topic: str, raw_payload: str) -> None:
        """Parse incoming JSON message and dispatch to the appropriate processor method."""
        try:
            data = json.loads(raw_payload)
            if not isinstance(data, dict):
                data = {"value": data}

            if topic.endswith("/count"):
                self.processor.process_count_payload(data)
            elif topic.endswith("/density"):
                self.processor.process_density_payload(data)
            elif topic.endswith("/alerts"):
                self.processor.process_alert_payload(data)
            elif topic.endswith("/command"):
                self.processor.process_command_payload(data)
            elif topic.startswith("ai/rooms/") and topic.endswith(
                "/telemetry"
            ):
                self.processor.process_combined_ai_telemetry(data)
        except Exception as exc:
            logger.error(
                "Error processing MQTT message on topic '%s': %s", topic, exc
            )

    def _on_gpio_state_changed(self, _new_state: Dict[str, Any]) -> None:
        self.publish_status()

    def _build_status_payload(self, status: str = "ONLINE") -> Dict[str, Any]:
        gpio_state = self.gpio.get_state()
        proc_summary = self.processor.get_summary()
        uptime_sec = int(max(0.0, time.monotonic() - self.started_at_mono))

        return {
            "deviceId": self.device_id,
            "deviceName": self.settings.IOT_DEVICE_NAME,
            "roomId": self.room_id,
            "ipAddress": self.gpio.get_local_ip(),
            "status": status,
            "simulationMode": self.gpio.is_simulation,
            "led": gpio_state["led"],
            "buzzer": gpio_state["buzzer"],
            "gpioConfig": self.gpio.get_gpio_config(),
            "gpioState": gpio_state,
            "occupancyMetrics": proc_summary,
            "cpuTemp": gpio_state["cpuTemp"],
            "uptimeSec": uptime_sec,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def publish_status(self) -> Dict[str, Any]:
        payload = self._build_status_payload(status="ONLINE")
        if self.client.is_connected():
            encoded = json.dumps(payload)
            self.client.publish(
                self.topic_device_status, encoded, qos=1, retain=True
            )
            self.client.publish(
                self.topic_legacy_status, encoded, qos=1, retain=True
            )
        return payload

    def _heartbeat_loop(self) -> None:
        interval = max(3, int(self.settings.IOT_HEARTBEAT_INTERVAL_SEC))
        while not self._stop_event.wait(interval):
            self.publish_status()
