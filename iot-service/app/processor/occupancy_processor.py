"""
Layer 2: Occupancy, Density & Alert Data Processor (`occupancy_processor.py`).
Decouples business rules from MQTT transport and GPIO hardware pins.
Evaluates incoming count, density, alert, and command payloads to produce
deterministic LED (GREEN / YELLOW / RED) and Buzzer actuation decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Dict, Literal, Optional

from app.config import IotSettings
from app.hardware.gpio_driver import BeepPattern, GpioController, LedColor
from app.logger import get_iot_logger

logger = get_iot_logger("iot.processor")

DensityLevelType = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AlertSeverityType = Literal["NONE", "WARNING", "CRITICAL"]


@dataclass
class ActuationDecision:
    led: LedColor
    buzzer: bool
    beep_pattern: BeepPattern
    duration_sec: int
    reason: str


class OccupancyDataProcessor:
    """
    Processes incoming occupancy count, crowd density, and alert payloads from AI Service
    and drives the GpioController accordingly.
    """

    def __init__(
        self,
        settings: IotSettings,
        gpio: GpioController,
    ) -> None:
        self.settings = settings
        self.gpio = gpio
        self._lock = threading.RLock()

        # Tracked room metrics
        self.current_count: int = 0
        self.max_capacity: int = settings.ROOM_MAX_CAPACITY
        self.current_density: float = 0.0
        self.density_level: DensityLevelType = "LOW"
        self.alert_severity: AlertSeverityType = "NONE"
        self.buzzer_silenced_by_operator: bool = False
        self.last_telemetry_ts: float = time.monotonic()

    def process_count_payload(
        self, payload: Dict[str, Any]
    ) -> ActuationDecision:
        """Process message from topic `occupancy/{room}/count`."""
        with self._lock:
            self.last_telemetry_ts = time.monotonic()
            if "totalCount" in payload:
                self.current_count = max(0, int(payload["totalCount"]))
            elif "current_count" in payload:
                self.current_count = max(0, int(payload["current_count"]))
            elif "count" in payload:
                self.current_count = max(0, int(payload["count"]))

            if "maxCapacity" in payload and int(payload["maxCapacity"]) > 0:
                self.max_capacity = int(payload["maxCapacity"])
            elif "max_capacity" in payload and int(payload["max_capacity"]) > 0:
                self.max_capacity = int(payload["max_capacity"])

            logger.info(
                "Received Occupancy Count -> %d / %d people",
                self.current_count,
                self.max_capacity,
            )
            return self._evaluate_and_actuate(source="count_update")

    def process_density_payload(
        self, payload: Dict[str, Any]
    ) -> ActuationDecision:
        """Process message from topic `occupancy/{room}/density`."""
        with self._lock:
            self.last_telemetry_ts = time.monotonic()
            if "roomDensity" in payload:
                self.current_density = float(payload["roomDensity"])
            elif "overall_density" in payload:
                self.current_density = float(payload["overall_density"])
            elif "density" in payload:
                self.current_density = float(payload["density"])

            raw_level = str(
                payload.get("densityLevel")
                or payload.get("alert_level")
                or ""
            ).upper()
            if raw_level == "WARNING":
                raw_level = "HIGH"
            elif raw_level == "NORMAL":
                raw_level = "LOW"
            if raw_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                self.density_level = raw_level  # type: ignore
            else:
                self.density_level = self._classify_density(
                    self.current_density
                )

            # Check if any zone inside `zones` array is in CRITICAL or HIGH state
            zones = payload.get("zones")
            if isinstance(zones, list):
                for z in zones:
                    z_lvl = str(z.get("densityLevel", "")).upper()
                    if z_lvl == "CRITICAL":
                        self.density_level = "CRITICAL"
                    elif z_lvl == "HIGH" and self.density_level not in (
                        "CRITICAL",
                    ):
                        self.density_level = "HIGH"

            logger.info(
                "Received Crowd Density -> %.3f people/m² (Level: %s)",
                self.current_density,
                self.density_level,
            )
            return self._evaluate_and_actuate(source="density_update")

    def process_alert_payload(
        self, payload: Dict[str, Any]
    ) -> ActuationDecision:
        """Process message from topic `occupancy/{room}/alerts`."""
        with self._lock:
            self.last_telemetry_ts = time.monotonic()
            severity = str(payload.get("severity", "NONE")).upper()
            status = str(payload.get("status", "ACTIVE")).upper()

            if status in ("RESOLVED", "CLEARED") or severity == "NONE":
                self.alert_severity = "NONE"
                self.buzzer_silenced_by_operator = False
            elif status == "ACKNOWLEDGED":
                self.buzzer_silenced_by_operator = True
                if severity in ("WARNING", "CRITICAL"):
                    self.alert_severity = severity  # type: ignore
            elif severity in ("WARNING", "CRITICAL"):
                if (
                    severity == "CRITICAL"
                    and self.alert_severity != "CRITICAL"
                ):
                    # New critical alert episode resets previous operator silence
                    self.buzzer_silenced_by_operator = False
                self.alert_severity = severity  # type: ignore

            logger.info(
                "Received Alert Event -> Severity=%s | Status=%s | Msg=%s",
                self.alert_severity,
                status,
                payload.get("message", ""),
            )
            return self._evaluate_and_actuate(source="alert_event")

    def process_combined_ai_telemetry(
        self, payload: Dict[str, Any]
    ) -> ActuationDecision:
        """Process unified telemetry payload from AI Service (`ai/rooms/+/telemetry`)."""
        with self._lock:
            self.last_telemetry_ts = time.monotonic()
            if "totalCount" in payload:
                self.current_count = max(0, int(payload["totalCount"]))
            if (
                "roomMaxCapacity" in payload
                and int(payload["roomMaxCapacity"]) > 0
            ):
                self.max_capacity = int(payload["roomMaxCapacity"])
            if "roomDensity" in payload:
                self.current_density = float(payload["roomDensity"])

            raw_level = str(
                payload.get("roomDensityLevel")
                or payload.get("densityLevel")
                or ""
            ).upper()
            if raw_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                self.density_level = raw_level  # type: ignore
            else:
                self.density_level = self._classify_density(
                    self.current_density
                )

            zones = payload.get("zones")
            if isinstance(zones, list):
                for z in zones:
                    z_lvl = str(z.get("densityLevel", "")).upper()
                    if z_lvl == "CRITICAL":
                        self.density_level = "CRITICAL"
                    elif z_lvl == "HIGH" and self.density_level != "CRITICAL":
                        self.density_level = "HIGH"

            active_alerts = payload.get("activeAlerts")
            if isinstance(active_alerts, list):
                if any(
                    str(a.get("severity", "")).upper() == "CRITICAL"
                    for a in active_alerts
                ):
                    if self.alert_severity != "CRITICAL":
                        self.buzzer_silenced_by_operator = False
                    self.alert_severity = "CRITICAL"
                elif any(
                    str(a.get("severity", "")).upper() == "WARNING"
                    for a in active_alerts
                ):
                    self.alert_severity = "WARNING"
                else:
                    self.alert_severity = "NONE"

            return self._evaluate_and_actuate(source="ai_telemetry")

    def process_command_payload(
        self, payload: Dict[str, Any]
    ) -> ActuationDecision:
        """
        Process direct device control command from `occupancy/{room}/device/command`
        or `iot/devices/{deviceId}/command`.
        """
        with self._lock:
            action = str(payload.get("action", "SET_STATE")).upper()

            if action == "SILENCE_BUZZER":
                self.buzzer_silenced_by_operator = True
                state = self.gpio.silence_buzzer(
                    reason="Operator issued SILENCE_BUZZER command"
                )
                return ActuationDecision(
                    led=state["led"],
                    buzzer=False,
                    beep_pattern="OFF",
                    duration_sec=0,
                    reason="SILENCE_BUZZER",
                )

            if action == "RESET":
                self.current_count = 0
                self.current_density = 0.0
                self.density_level = "LOW"
                self.alert_severity = "NONE"
                self.buzzer_silenced_by_operator = False
                return self._evaluate_and_actuate(source="command_reset")

            # Explicit LED / Buzzer command override
            led_raw = str(
                payload.get("led")
                or payload.get("ledState")
                or payload.get("led_state")
                or "GREEN"
            ).upper()
            led: LedColor = (
                led_raw  # type: ignore
                if led_raw in ("GREEN", "YELLOW", "RED", "OFF")
                else "GREEN"
            )
            if "buzzer" in payload:
                buzzer = bool(payload["buzzer"])
            elif "buzzerActive" in payload:
                buzzer = bool(payload["buzzerActive"])
            elif "buzzer_active" in payload:
                buzzer = bool(payload["buzzer_active"])
            else:
                buzzer = False
            if not buzzer and led == "RED":
                self.buzzer_silenced_by_operator = True

            beep_raw = str(
                payload.get("beepPattern", "PULSE" if buzzer else "OFF")
            ).upper()
            beep_pattern: BeepPattern = (
                beep_raw  # type: ignore
                if beep_raw in ("OFF", "PULSE", "CONTINUOUS")
                else "PULSE"
            )
            duration_sec = int(
                payload.get(
                    "durationSec", self.settings.BUZZER_MAX_DURATION_SEC
                )
            )
            reason = str(payload.get("reason", f"MQTT Command ({action})"))

            self.gpio.set_state(
                led=led,
                buzzer=buzzer,
                beep_pattern=beep_pattern,
                duration_sec=duration_sec,
                reason=reason,
            )
            return ActuationDecision(
                led=led,
                buzzer=buzzer,
                beep_pattern=beep_pattern,
                duration_sec=duration_sec,
                reason=reason,
            )

    def _classify_density(self, density: float) -> DensityLevelType:
        if density >= self.settings.CRITICAL_DENSITY_THRESHOLD:
            return "CRITICAL"
        if density >= self.settings.WARNING_DENSITY_THRESHOLD:
            return "HIGH"
        if density >= self.settings.WARNING_DENSITY_THRESHOLD * 0.5:
            return "MEDIUM"
        return "LOW"

    def _evaluate_and_actuate(self, source: str) -> ActuationDecision:
        """
        Determine target LED color and Buzzer state from current metrics:
        - CRITICAL: Red LED + Buzzer PULSE
        - WARNING / HIGH: Yellow LED + Buzzer OFF
        - NORMAL (LOW / MEDIUM): Green LED + Buzzer OFF
        """
        warn_count = max(
            1,
            int(
                round(self.max_capacity * self.settings.WARNING_OCCUPANCY_RATIO)
            ),
        )
        is_critical = (
            self.alert_severity == "CRITICAL"
            or self.density_level == "CRITICAL"
            or self.current_count >= self.max_capacity
            or self.current_density >= self.settings.CRITICAL_DENSITY_THRESHOLD
        )
        is_warning = (
            not is_critical
            and (
                self.alert_severity == "WARNING"
                or self.density_level == "HIGH"
                or self.current_count >= warn_count
                or self.current_density
                >= self.settings.WARNING_DENSITY_THRESHOLD
            )
        )

        if is_critical:
            target_led: LedColor = "RED"
            target_buzzer = not self.buzzer_silenced_by_operator
            target_pattern: BeepPattern = "PULSE" if target_buzzer else "OFF"
            reason = (
                f"CRITICAL threshold exceeded ({source}: count={self.current_count}/{self.max_capacity}, "
                f"density={self.current_density:.2f}/m², level={self.density_level})"
            )
        elif is_warning:
            self.buzzer_silenced_by_operator = False
            target_led = "YELLOW"
            target_buzzer = False
            target_pattern = "OFF"
            reason = (
                f"Near threshold WARNING ({source}: count={self.current_count}/{self.max_capacity}, "
                f"density={self.current_density:.2f}/m², level={self.density_level})"
            )
        else:
            self.buzzer_silenced_by_operator = False
            target_led = "GREEN"
            target_buzzer = False
            target_pattern = "OFF"
            reason = (
                f"Normal occupancy ({source}: count={self.current_count}/{self.max_capacity}, "
                f"density={self.current_density:.2f}/m²)"
            )

        current_gpio = self.gpio.get_state()
        if (
            current_gpio["led"] != target_led
            or current_gpio["buzzer"] != target_buzzer
        ):
            self.gpio.set_state(
                led=target_led,
                buzzer=target_buzzer,
                beep_pattern=target_pattern,
                duration_sec=(
                    self.settings.BUZZER_MAX_DURATION_SEC
                    if target_buzzer
                    else 0
                ),
                reason=reason,
            )

        return ActuationDecision(
            led=target_led,
            buzzer=target_buzzer,
            beep_pattern=target_pattern,
            duration_sec=(
                self.settings.BUZZER_MAX_DURATION_SEC if target_buzzer else 0
            ),
            reason=reason,
        )

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "currentCount": self.current_count,
                "maxCapacity": self.max_capacity,
                "currentDensity": round(self.current_density, 4),
                "densityLevel": self.density_level,
                "alertSeverity": self.alert_severity,
                "buzzerSilenced": self.buzzer_silenced_by_operator,
                "secondsSinceLastTelemetry": round(
                    max(0.0, time.monotonic() - self.last_telemetry_ts), 1
                ),
            }
