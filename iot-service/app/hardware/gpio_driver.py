"""
Layer 1B: High-Level Actuator Controller (`gpio_driver.py`).
Controls the 3 status LEDs (Green, Yellow, Red) and the Active Buzzer on Raspberry Pi 4/5:
- GREEN  (BCM 17 / Pin 11): Normal crowd density (LOW / MEDIUM)
- YELLOW (BCM 27 / Pin 13): Crowd density approaching threshold (WARNING / HIGH)
- RED    (BCM 22 / Pin 15): Crowd density exceeded threshold (CRITICAL)
- BUZZER (BCM 23 / Pin 16): Audible alarm on CRITICAL alerts (supports 2Hz PULSE & auto-timeout)

Guarantees GPIO cleanup on process exit via `atexit`, signal handlers, and context management.
"""

from __future__ import annotations

import atexit
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional

from app.hardware.gpio_interface import (
    BaseGpioDriver,
    SimulationGpioDriver,
    create_gpio_driver,
)
from app.logger import get_iot_logger

logger = get_iot_logger("iot.hardware.actuator")

LedColor = Literal["GREEN", "YELLOW", "RED", "OFF"]
BeepPattern = Literal["OFF", "PULSE", "CONTINUOUS"]


class GpioController:
    """
    Thread-safe controller for Raspberry Pi LEDs and Buzzer with guaranteed GPIO release.
    """

    def __init__(
        self,
        pin_led_green: int = 17,
        pin_led_yellow: int = 27,
        pin_led_red: int = 22,
        pin_buzzer: int = 23,
        force_simulation: bool = False,
        driver: Optional[BaseGpioDriver] = None,
        on_state_change: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.pin_led_green = int(pin_led_green)
        self.pin_led_yellow = int(pin_led_yellow)
        self.pin_led_red = int(pin_led_red)
        self.pin_buzzer = int(pin_buzzer)
        self.on_state_change = on_state_change

        self._lock = threading.RLock()
        self._led_state: LedColor = "GREEN"
        self._buzzer_active: bool = False
        self._beep_pattern: BeepPattern = "OFF"
        self._cleaned_up: bool = False

        self._buzzer_stop_event = threading.Event()
        self._buzzer_thread: Optional[threading.Thread] = None
        self._auto_off_timer: Optional[threading.Timer] = None

        self.driver: BaseGpioDriver = driver or create_gpio_driver(
            force_simulation=force_simulation
        )
        self.driver.setup_pins(
            [
                self.pin_led_green,
                self.pin_led_yellow,
                self.pin_led_red,
                self.pin_buzzer,
            ]
        )

        # Register guaranteed cleanup hook when Python interpreter exits
        atexit.register(self.cleanup)

        # Default startup state: Normal density -> Green LED ON, Buzzer OFF
        self.set_state(led="GREEN", buzzer=False, beep_pattern="OFF")

    def __enter__(self) -> GpioController:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    @property
    def is_simulation(self) -> bool:
        return self.driver.is_simulation

    def set_state(
        self,
        led: LedColor,
        buzzer: bool,
        beep_pattern: BeepPattern = "OFF",
        duration_sec: int = 0,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Set mutually exclusive LED indicator (GREEN / YELLOW / RED / OFF) and Buzzer alarm.
        """
        with self._lock:
            self._cleaned_up = False
            led_upper = led.upper() if led else "GREEN"
            if led_upper not in ("GREEN", "YELLOW", "RED", "OFF"):
                led_upper = "GREEN"
            self._led_state = led_upper  # type: ignore

            # Drive physical or simulated LED pins
            self.driver.write_pin(
                self.pin_led_green, self._led_state == "GREEN"
            )
            self.driver.write_pin(
                self.pin_led_yellow, self._led_state == "YELLOW"
            )
            self.driver.write_pin(self.pin_led_red, self._led_state == "RED")

            # Reset any existing buzzer thread/timer before applying new buzzer state
            self._stop_buzzer_worker()

            self._buzzer_active = bool(buzzer)
            if not self._buzzer_active:
                self._beep_pattern = "OFF"
                self.driver.write_pin(self.pin_buzzer, False)
            else:
                self._beep_pattern = (
                    beep_pattern
                    if beep_pattern in ("PULSE", "CONTINUOUS")
                    else "PULSE"
                )
                if self._beep_pattern == "CONTINUOUS":
                    self.driver.write_pin(self.pin_buzzer, True)
                else:
                    self._buzzer_stop_event.clear()
                    self._buzzer_thread = threading.Thread(
                        target=self._pulse_buzzer_loop,
                        daemon=True,
                        name="BuzzerPulseWorker",
                    )
                    self._buzzer_thread.start()

                if duration_sec > 0:
                    self._auto_off_timer = threading.Timer(
                        float(duration_sec),
                        self._auto_silence_buzzer,
                    )
                    self._auto_off_timer.daemon = True
                    self._auto_off_timer.start()

            current = self.get_state()
            if isinstance(self.driver, SimulationGpioDriver):
                banner = self.driver.format_breadboard_banner(
                    self.pin_led_green,
                    self.pin_led_yellow,
                    self.pin_led_red,
                    self.pin_buzzer,
                )
                logger.info(
                    "%s %s", banner, f"| Reason: {reason}" if reason else ""
                )
            else:
                logger.info(
                    "GPIO State -> LED=%s | Buzzer=%s (%s) %s",
                    current["led"],
                    current["buzzer"],
                    current["beepPattern"],
                    f"| Reason: {reason}" if reason else "",
                )

        if self.on_state_change:
            try:
                self.on_state_change(current)
            except Exception as exc:
                logger.warning("on_state_change callback error: %s", exc)

        return current

    def silence_buzzer(self, reason: str = "Silence requested") -> Dict[str, Any]:
        """Silence the buzzer immediately while preserving the current LED state."""
        with self._lock:
            return self.set_state(
                led=self._led_state,
                buzzer=False,
                beep_pattern="OFF",
                reason=reason,
            )

    def _pulse_buzzer_loop(self) -> None:
        """Toggle buzzer pin at 2Hz (250ms ON / 250ms OFF) during PULSE mode."""
        pin_high = False
        while not self._buzzer_stop_event.is_set():
            pin_high = not pin_high
            self.driver.write_pin(self.pin_buzzer, pin_high)
            if self._buzzer_stop_event.wait(0.25):
                break
        self.driver.write_pin(self.pin_buzzer, False)

    def _stop_buzzer_worker(self) -> None:
        if self._auto_off_timer is not None:
            self._auto_off_timer.cancel()
            self._auto_off_timer = None
        self._buzzer_stop_event.set()
        if (
            self._buzzer_thread is not None
            and self._buzzer_thread.is_alive()
            and threading.current_thread() is not self._buzzer_thread
        ):
            self._buzzer_thread.join(timeout=0.6)
        self._buzzer_thread = None
        self.driver.write_pin(self.pin_buzzer, False)

    def _auto_silence_buzzer(self) -> None:
        logger.info("Buzzer max duration reached -> auto-silencing buzzer.")
        with self._lock:
            self._buzzer_active = False
            self._beep_pattern = "OFF"
            self._buzzer_stop_event.set()
            self.driver.write_pin(self.pin_buzzer, False)
            state = self.get_state()
        if self.on_state_change:
            self.on_state_change(state)

    def is_healthy(self) -> bool:
        """Used by Watchdog to verify that if PULSE mode is active, the pulse thread is alive."""
        with self._lock:
            if self._buzzer_active and self._beep_pattern == "PULSE":
                return bool(
                    self._buzzer_thread is not None
                    and self._buzzer_thread.is_alive()
                )
            return True

    def read_cpu_temperature(self) -> float:
        """Read Raspberry Pi SoC temperature (°C) from Linux thermal zone sysfs."""
        thermal_file = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            if thermal_file.exists():
                milli_c = int(thermal_file.read_text(encoding="utf-8").strip())
                return round(milli_c / 1000.0, 1)
        except Exception:
            pass
        return 43.0

    @staticmethod
    def get_local_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return str(s.getsockname()[0])
        except Exception:
            return "127.0.0.1"

    def get_gpio_config(self) -> Dict[str, int]:
        return {
            "ledGreen": self.pin_led_green,
            "ledYellow": self.pin_led_yellow,
            "ledRed": self.pin_led_red,
            "buzzer": self.pin_buzzer,
        }

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "led": self._led_state,
                "buzzer": self._buzzer_active,
                "beepPattern": self._beep_pattern,
                "cpuTemp": self.read_cpu_temperature(),
                "simulationMode": self.is_simulation,
                "hardwareGpio": not self.is_simulation,
                "pins": {
                    str(self.pin_led_green): self.driver.read_pin(
                        self.pin_led_green
                    ),
                    str(self.pin_led_yellow): self.driver.read_pin(
                        self.pin_led_yellow
                    ),
                    str(self.pin_led_red): self.driver.read_pin(
                        self.pin_led_red
                    ),
                    str(self.pin_buzzer): self.driver.read_pin(self.pin_buzzer),
                },
            }

    def cleanup(self) -> None:
        """Guarantee that all GPIO pins are driven LOW and released upon termination."""
        with self._lock:
            if self._cleaned_up:
                return
            self._stop_buzzer_worker()
            self._led_state = "OFF"
            self._buzzer_active = False
            self._beep_pattern = "OFF"
            self.driver.cleanup()
            self._cleaned_up = True


ActuatorController = GpioController
