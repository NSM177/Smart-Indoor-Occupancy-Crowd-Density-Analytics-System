"""
Unit Test Suite for the Raspberry Pi 4/5 IoT Edge Module (`tests/test_iot_module.py`).
Tests:
1. SimulationGpioDriver pin logic levels & guaranteed cleanup on exit.
2. GpioController mutually exclusive LED states (GREEN, YELLOW, RED) & Buzzer pulse/timeout.
3. OccupancyDataProcessor transitions across `count`, `density`, `alerts`, and `command` payloads.
4. IotMqttAgent topic routing for `occupancy/room1/count`, `occupancy/room1/density`,
   `occupancy/room1/alerts`, `occupancy/room1/device/command`, and status payload generation.
5. ServiceWatchdog health check & stalled buzzer worker recovery.
"""

from __future__ import annotations

import json
import time
import unittest

from app.config import IotSettings
from app.hardware.gpio_driver import GpioController
from app.hardware.gpio_interface import SimulationGpioDriver
from app.mqtt.client import IotMqttAgent
from app.processor.occupancy_processor import OccupancyDataProcessor
from app.watchdog.supervisor import ServiceWatchdog


class TestIotModule(unittest.TestCase):
    """Comprehensive tests for GPIO, Processor, MQTT Topic Routing, and Watchdog."""

    def setUp(self) -> None:
        self.test_settings = IotSettings(
            IOT_DEVICE_ID="TEST_RPI_01",
            IOT_ROOM_ID="room1",
            GPIO_PIN_LED_GREEN=17,
            GPIO_PIN_LED_YELLOW=27,
            GPIO_PIN_LED_RED=22,
            GPIO_PIN_BUZZER=23,
            SIMULATION_MODE=True,
            ROOM_MAX_CAPACITY=50,
            WARNING_OCCUPANCY_RATIO=0.80,
            WARNING_DENSITY_THRESHOLD=0.35,
            CRITICAL_DENSITY_THRESHOLD=0.50,
            BUZZER_MAX_DURATION_SEC=2,
        )

    def test_simulation_gpio_driver_and_cleanup_guarantee(self) -> None:
        sim_driver = SimulationGpioDriver()
        with GpioController(
            pin_led_green=17,
            pin_led_yellow=27,
            pin_led_red=22,
            pin_buzzer=23,
            driver=sim_driver,
        ) as gpio:
            # Initial state is GREEN ON (pin 17 HIGH, others LOW)
            self.assertTrue(sim_driver.read_pin(17))
            self.assertFalse(sim_driver.read_pin(27))
            self.assertFalse(sim_driver.read_pin(22))
            self.assertFalse(sim_driver.read_pin(23))

            # Switch to YELLOW
            gpio.set_state(led="YELLOW", buzzer=False)
            self.assertFalse(sim_driver.read_pin(17))
            self.assertTrue(sim_driver.read_pin(27))
            self.assertFalse(sim_driver.read_pin(22))

            # Switch to RED + CONTINUOUS Buzzer
            gpio.set_state(
                led="RED", buzzer=True, beep_pattern="CONTINUOUS"
            )
            self.assertFalse(sim_driver.read_pin(17))
            self.assertFalse(sim_driver.read_pin(27))
            self.assertTrue(sim_driver.read_pin(22))
            self.assertTrue(sim_driver.read_pin(23))

        # Exiting context manager guarantees all GPIO pins are driven LOW (0V)
        self.assertTrue(sim_driver.cleaned_up)
        self.assertFalse(sim_driver.read_pin(17))
        self.assertFalse(sim_driver.read_pin(27))
        self.assertFalse(sim_driver.read_pin(22))
        self.assertFalse(sim_driver.read_pin(23))

    def test_occupancy_processor_led_and_buzzer_decisions(self) -> None:
        with GpioController(force_simulation=True) as gpio:
            proc = OccupancyDataProcessor(
                settings=self.test_settings, gpio=gpio
            )

            # 1. Normal count (20 / 50) & low density (0.15) -> GREEN LED, Buzzer OFF
            d1 = proc.process_count_payload(
                {"totalCount": 20, "maxCapacity": 50}
            )
            self.assertEqual(d1.led, "GREEN")
            self.assertFalse(d1.buzzer)

            # 2. Count nears threshold (42 / 50 >= 80%) -> YELLOW LED, Buzzer OFF
            d2 = proc.process_count_payload(
                {"totalCount": 42, "maxCapacity": 50}
            )
            self.assertEqual(d2.led, "YELLOW")
            self.assertFalse(d2.buzzer)

            # 3. Density exceeds critical threshold (0.55 >= 0.50) -> RED LED, Buzzer ON
            d3 = proc.process_density_payload(
                {"roomDensity": 0.55, "densityLevel": "CRITICAL"}
            )
            self.assertEqual(d3.led, "RED")
            self.assertTrue(d3.buzzer)

            # 4. Operator silences buzzer -> RED LED remains ON, Buzzer turns OFF
            d4 = proc.process_command_payload({"action": "SILENCE_BUZZER"})
            self.assertEqual(d4.led, "RED")
            self.assertFalse(d4.buzzer)

            # 5. Count & density drop back to normal -> GREEN LED, Buzzer OFF
            proc.process_count_payload({"totalCount": 12, "maxCapacity": 50})
            d5 = proc.process_density_payload(
                {"roomDensity": 0.10, "densityLevel": "LOW"}
            )
            self.assertEqual(d5.led, "GREEN")
            self.assertFalse(d5.buzzer)

    def test_mqtt_topic_routing_and_status_payload(self) -> None:
        with GpioController(force_simulation=True) as gpio:
            proc = OccupancyDataProcessor(
                settings=self.test_settings, gpio=gpio
            )
            agent = IotMqttAgent(
                settings=self.test_settings,
                gpio_controller=gpio,
                processor=proc,
            )

            # Route `occupancy/room1/count`
            agent.route_topic_message(
                "occupancy/room1/count",
                json.dumps({"totalCount": 45, "maxCapacity": 50}),
            )
            self.assertEqual(gpio.get_state()["led"], "YELLOW")

            # Route `occupancy/room1/alerts` with CRITICAL severity
            agent.route_topic_message(
                "occupancy/room1/alerts",
                json.dumps(
                    {
                        "severity": "CRITICAL",
                        "status": "ACTIVE",
                        "message": "Overcrowding in Zone B",
                    }
                ),
            )
            self.assertEqual(gpio.get_state()["led"], "RED")
            self.assertTrue(gpio.get_state()["buzzer"])

            # Route `occupancy/room1/device/command` RESET
            agent.route_topic_message(
                "occupancy/room1/device/command",
                json.dumps({"action": "RESET"}),
            )
            self.assertEqual(gpio.get_state()["led"], "GREEN")
            self.assertFalse(gpio.get_state()["buzzer"])

            status = agent.publish_status()
            self.assertEqual(status["roomId"], "room1")
            self.assertEqual(status["deviceId"], "TEST_RPI_01")
            self.assertTrue(status["simulationMode"])

    def test_watchdog_buzzer_worker_recovery(self) -> None:
        with GpioController(force_simulation=True) as gpio:
            proc = OccupancyDataProcessor(
                settings=self.test_settings, gpio=gpio
            )
            agent = IotMqttAgent(
                settings=self.test_settings,
                gpio_controller=gpio,
                processor=proc,
            )
            watchdog = ServiceWatchdog(
                settings=self.test_settings,
                gpio=gpio,
                processor=proc,
                mqtt_agent=agent,
            )

            # Activate PULSE buzzer
            gpio.set_state(
                led="RED", buzzer=True, beep_pattern="PULSE", duration_sec=10
            )
            self.assertTrue(gpio.is_healthy())

            # Simulate unexpected thread failure by stopping the internal pulse thread while _buzzer_active=True
            gpio._buzzer_stop_event.set()
            time.sleep(0.3)
            self.assertFalse(gpio.is_healthy())

            # Watchdog detects stalled buzzer thread and recovers it automatically
            watchdog.run_health_check_once()
            self.assertEqual(watchdog.recovery_count, 1)
            self.assertTrue(gpio.is_healthy())


if __name__ == "__main__":
    unittest.main()
