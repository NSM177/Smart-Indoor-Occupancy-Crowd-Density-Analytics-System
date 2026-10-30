"""
Layer 1A: GPIO Hardware Abstraction & Simulation Layer (`gpio_interface.py`).
Separates low-level BCM pin I/O from high-level LED/Buzzer actuation logic.
Provides:
- `BaseGpioDriver`: Abstract interface for digital output pins.
- `RPiHardwareGpioDriver`: Physical Raspberry Pi 4 (`RPi.GPIO`) and Raspberry Pi 5 (`gpiozero`/`lgpio`) driver.
- `SimulationGpioDriver`: Visual Breadboard Simulator for testing on PC/Docker without physical hardware.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Tuple

from app.logger import get_iot_logger

logger = get_iot_logger("iot.hardware.gpio_interface")


class BaseGpioDriver(ABC):
    """Abstract interface for Raspberry Pi BCM GPIO pin operations."""

    @property
    @abstractmethod
    def is_simulation(self) -> bool:
        """Return True if operating in software simulation mode."""

    @abstractmethod
    def setup_pins(self, pins: Iterable[int]) -> None:
        """Configure specified BCM pins as digital outputs initialized to LOW (0V)."""

    @abstractmethod
    def write_pin(self, pin: int, high: bool) -> None:
        """Drive a BCM pin HIGH (3.3V) or LOW (0V)."""

    @abstractmethod
    def read_pin(self, pin: int) -> bool:
        """Return current logic level (True=HIGH, False=LOW) of a BCM pin."""

    @abstractmethod
    def cleanup(self) -> None:
        """Drive all managed pins LOW and release OS GPIO handles."""


class SimulationGpioDriver(BaseGpioDriver):
    """
    Simulated Breadboard GPIO Driver.
    Tracks digital logic levels (0V / 3.3V) of every configured BCM pin and logs
    visual LED/Buzzer breadboard indicators for standalone verification.
    """

    def __init__(self, pin_labels: Dict[int, str] | None = None) -> None:
        self._pin_states: Dict[int, bool] = {}
        self._pin_labels: Dict[int, str] = pin_labels or {}
        self.transition_history: List[Tuple[int, bool]] = []
        self.cleaned_up: bool = False

    @property
    def is_simulation(self) -> bool:
        return True

    def setup_pins(self, pins: Iterable[int]) -> None:
        self.cleaned_up = False
        for p in pins:
            self._pin_states[int(p)] = False
        logger.info(
            "[SIMULATION GPIO] Configured BCM output pins (initial=LOW/0V): %s",
            sorted(self._pin_states.keys()),
        )

    def write_pin(self, pin: int, high: bool) -> None:
        pin_int = int(pin)
        prev = self._pin_states.get(pin_int)
        self._pin_states[pin_int] = bool(high)
        if prev != bool(high):
            self.transition_history.append((pin_int, bool(high)))

    def read_pin(self, pin: int) -> bool:
        return bool(self._pin_states.get(int(pin), False))

    def format_breadboard_banner(
        self,
        pin_green: int,
        pin_yellow: int,
        pin_red: int,
        pin_buzzer: int,
    ) -> str:
        g_on = self.read_pin(pin_green)
        y_on = self.read_pin(pin_yellow)
        r_on = self.read_pin(pin_red)
        b_on = self.read_pin(pin_buzzer)
        return (
            f"[BREADBOARD SIM] "
            f"GPIO{pin_green}(GREEN)={'ON (3.3V)' if g_on else 'OFF(0.0V)'} | "
            f"GPIO{pin_yellow}(YELLOW)={'ON (3.3V)' if y_on else 'OFF(0.0V)'} | "
            f"GPIO{pin_red}(RED)={'ON (3.3V)' if r_on else 'OFF(0.0V)'} | "
            f"GPIO{pin_buzzer}(BUZZER)={'ACTIVE' if b_on else 'SILENT'}"
        )

    def cleanup(self) -> None:
        for p in list(self._pin_states.keys()):
            self._pin_states[p] = False
        self.cleaned_up = True
        logger.info(
            "[SIMULATION GPIO] All BCM pins driven LOW (0V) and released cleanly."
        )


class RPiHardwareGpioDriver(BaseGpioDriver):
    """
    Physical Raspberry Pi 4/5 GPIO Driver.
    Supports `RPi.GPIO` (Raspberry Pi 4) and `gpiozero` / `lgpio` (Raspberry Pi 5 RP1 chip).
    """

    def __init__(self) -> None:
        self._pin_states: Dict[int, bool] = {}
        self._backend_type: str = "none"
        self._rpi_gpio: Any = None
        self._gpiozero_devices: Dict[int, Any] = {}
        self._detect_and_bind()

    def _detect_and_bind(self) -> None:
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            self._rpi_gpio = GPIO
            self._backend_type = "RPi.GPIO"
            return
        except Exception:
            pass

        try:
            from gpiozero import DigitalOutputDevice  # type: ignore

            self._backend_type = "gpiozero"
            self._digital_out_cls = DigitalOutputDevice
            return
        except Exception as exc:
            raise RuntimeError(
                f"No physical Raspberry Pi GPIO backend (RPi.GPIO / gpiozero) available: {exc}"
            ) from exc

    @property
    def is_simulation(self) -> bool:
        return False

    def setup_pins(self, pins: Iterable[int]) -> None:
        for pin in pins:
            p = int(pin)
            self._pin_states[p] = False
            if self._backend_type == "RPi.GPIO":
                self._rpi_gpio.setup(
                    p, self._rpi_gpio.OUT, initial=self._rpi_gpio.LOW
                )
            elif self._backend_type == "gpiozero":
                dev = self._digital_out_cls(p, active_high=True, initial_value=False)
                self._gpiozero_devices[p] = dev

        logger.info(
            "[HARDWARE GPIO - %s] Initialized physical BCM pins: %s",
            self._backend_type,
            sorted(self._pin_states.keys()),
        )

    def write_pin(self, pin: int, high: bool) -> None:
        p = int(pin)
        self._pin_states[p] = bool(high)
        if self._backend_type == "RPi.GPIO" and self._rpi_gpio is not None:
            level = self._rpi_gpio.HIGH if high else self._rpi_gpio.LOW
            self._rpi_gpio.output(p, level)
        elif self._backend_type == "gpiozero":
            dev = self._gpiozero_devices.get(p)
            if dev is not None:
                if high:
                    dev.on()
                else:
                    dev.off()

    def read_pin(self, pin: int) -> bool:
        return bool(self._pin_states.get(int(pin), False))

    def cleanup(self) -> None:
        for p in list(self._pin_states.keys()):
            try:
                self.write_pin(p, False)
            except Exception:
                pass

        if self._backend_type == "RPi.GPIO" and self._rpi_gpio is not None:
            try:
                self._rpi_gpio.cleanup()
            except Exception:
                pass
        elif self._backend_type == "gpiozero":
            for dev in self._gpiozero_devices.values():
                try:
                    dev.close()
                except Exception:
                    pass
            self._gpiozero_devices.clear()

        logger.info(
            "[HARDWARE GPIO - %s] Released all physical BCM GPIO pins.",
            self._backend_type,
        )


def create_gpio_driver(force_simulation: bool = False) -> BaseGpioDriver:
    """
    Factory that returns `SimulationGpioDriver` if `force_simulation=True` or if
    not running on a physical Raspberry Pi board; otherwise returns `RPiHardwareGpioDriver`.
    """
    if force_simulation:
        logger.info("Simulation Mode explicitly enabled via configuration.")
        return SimulationGpioDriver()

    try:
        return RPiHardwareGpioDriver()
    except Exception:
        logger.info(
            "Physical Raspberry Pi GPIO hardware not detected -> activating SimulationGpioDriver."
        )
        return SimulationGpioDriver()
