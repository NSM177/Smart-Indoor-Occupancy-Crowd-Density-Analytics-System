"""
Layer 4: Service Watchdog & Fault Recovery Supervisor (`supervisor.py`).
Monitors:
1. MQTT Broker connectivity & triggers automatic reconnect recovery if disconnected.
2. GPIO & Buzzer pulse worker thread health (re-initializes buzzer thread if stalled).
3. Stale AI Service telemetry timeout (if no MQTT messages arrive within `stale_timeout_sec`,
   attempts HTTP fallback polling from `AI_SERVICE_URL/analytics/current`).
4. Linux `systemd` watchdog heartbeat (`sd_notify("WATCHDOG=1")`) when running on Raspberry Pi OS.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from typing import Optional

from app.config import IotSettings
from app.hardware.camera_streamer import CameraConnector
from app.hardware.gpio_driver import GpioController
from app.logger import get_iot_logger
from app.mqtt.client import IotMqttAgent
from app.processor.occupancy_processor import OccupancyDataProcessor

logger = get_iot_logger("iot.watchdog")


class ServiceWatchdog:
    """Supervises IoT module health and executes automatic fault recovery."""

    def __init__(
        self,
        settings: IotSettings,
        gpio: GpioController,
        processor: OccupancyDataProcessor,
        mqtt_agent: IotMqttAgent,
        camera_connector: Optional[CameraConnector] = None,
    ) -> None:
        self.settings = settings
        self.gpio = gpio
        self.processor = processor
        self.mqtt_agent = mqtt_agent
        self.camera = camera_connector or CameraConnector(
            camera_source=settings.CAMERA_SOURCE,
            ai_service_url=settings.AI_SERVICE_URL,
            simulation_mode=gpio.is_simulation,
        )

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.recovery_count: int = 0
        self.last_check_ts: float = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="IotServiceWatchdog",
        )
        self._thread.start()
        logger.info(
            "ServiceWatchdog started (check_interval=%ds, stale_timeout=%ds)",
            self.settings.WATCHDOG_CHECK_INTERVAL_SEC,
            self.settings.TELEMETRY_STALE_TIMEOUT_SEC,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def run_health_check_once(self) -> bool:
        """
        Execute one full health inspection and recovery cycle.
        Returns True if all subsystems are healthy or successfully recovered.
        """
        self.last_check_ts = time.monotonic()
        all_healthy = True

        # 1. Verify GPIO / Buzzer worker health
        if not self.gpio.is_healthy():
            all_healthy = False
            self.recovery_count += 1
            logger.warning(
                "[WATCHDOG] Buzzer pulse worker stalled -> recovering GPIO state..."
            )
            current = self.gpio.get_state()
            self.gpio.set_state(
                led=current["led"],
                buzzer=current["buzzer"],
                beep_pattern=current["beepPattern"],
                duration_sec=self.settings.BUZZER_MAX_DURATION_SEC,
                reason="Watchdog buzzer worker recovery",
            )

        # 2. Verify MQTT Broker connection
        if not self.mqtt_agent.client.is_connected():
            self.mqtt_agent.check_and_recover_connection()

        # 3. Check if AI telemetry is stale -> fallback poll AI Service over HTTP
        summary = self.processor.get_summary()
        stale_sec = float(summary.get("secondsSinceLastTelemetry", 0.0))
        if stale_sec >= float(self.settings.TELEMETRY_STALE_TIMEOUT_SEC):
            fallback_data = self.camera.fetch_ai_service_analytics()
            if fallback_data is not None:
                logger.info(
                    "[WATCHDOG] Retrieved telemetry via HTTP fallback from AI Service."
                )
                self.processor.process_combined_ai_telemetry(fallback_data)

        # 4. Notify Linux systemd watchdog if NOTIFY_SOCKET is set on Raspberry Pi OS
        self._notify_systemd_watchdog()
        return all_healthy

    def _watchdog_loop(self) -> None:
        interval = max(2, int(self.settings.WATCHDOG_CHECK_INTERVAL_SEC))
        while not self._stop_event.wait(interval):
            try:
                self.run_health_check_once()
            except Exception as exc:
                logger.error("[WATCHDOG] Unexpected error during check: %s", exc)

    @staticmethod
    def _notify_systemd_watchdog() -> None:
        notify_socket = os.environ.get("NOTIFY_SOCKET")
        if not notify_socket:
            return
        if notify_socket.startswith("@"):
            notify_socket = "\0" + notify_socket[1:]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.connect(notify_socket)
                sock.sendall(b"WATCHDOG=1")
        except Exception:
            pass
