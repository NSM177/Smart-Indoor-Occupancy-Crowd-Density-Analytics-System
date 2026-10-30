"""
Main Entrypoint for the Raspberry Pi 4/5 IoT Edge Service (`main.py`).
Coordinates:
- Layer 1: GPIO Hardware / Simulation Controller (`GpioController`) & Camera Connector
- Layer 2: Occupancy, Density & Alert Processor (`OccupancyDataProcessor`)
- Layer 3: MQTT Client with Auto-Reconnect & LWT (`IotMqttAgent`)
- Layer 4: Watchdog & Fault Recovery Supervisor (`ServiceWatchdog`)

CLI Modes:
- `python -m app.main`               : Run production IoT service connected to Mosquitto
- `python -m app.main --simulate`    : Run end-to-end Simulation Demo without hardware/broker
- `python -m app.main --self-test`   : Run quick GPIO & processor verification and exit
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from types import FrameType

from app.config import settings
from app.hardware.camera_streamer import CameraConnector
from app.hardware.gpio_driver import GpioController
from app.logger import get_iot_logger, setup_iot_logging
from app.mqtt.client import IotMqttAgent
from app.processor.occupancy_processor import OccupancyDataProcessor
from app.watchdog.supervisor import ServiceWatchdog

setup_iot_logging()
logger = get_iot_logger("iot.main")


def run_simulation_scenario() -> int:
    """
    Execute a complete interactive simulation of all MQTT topics, LED transitions,
    Buzzer alarm patterns, Watchdog checks, and guaranteed GPIO release.
    """
    logger.info("==================================================================")
    logger.info("STARTING RASPBERRY PI 4/5 IOT MODULE - SIMULATION MODE")
    logger.info(
        "Pin Mapping (BCM): GREEN=%d (Pin 11), YELLOW=%d (Pin 13), RED=%d (Pin 15), BUZZER=%d (Pin 16)",
        settings.GPIO_PIN_LED_GREEN,
        settings.GPIO_PIN_LED_YELLOW,
        settings.GPIO_PIN_LED_RED,
        settings.GPIO_PIN_BUZZER,
    )
    logger.info("==================================================================")

    with GpioController(
        pin_led_green=settings.GPIO_PIN_LED_GREEN,
        pin_led_yellow=settings.GPIO_PIN_LED_YELLOW,
        pin_led_red=settings.GPIO_PIN_LED_RED,
        pin_buzzer=settings.GPIO_PIN_BUZZER,
        force_simulation=True,
    ) as gpio:
        processor = OccupancyDataProcessor(settings=settings, gpio=gpio)
        agent = IotMqttAgent(
            settings=settings, gpio_controller=gpio, processor=processor
        )
        watchdog = ServiceWatchdog(
            settings=settings,
            gpio=gpio,
            processor=processor,
            mqtt_agent=agent,
        )

        room = settings.IOT_ROOM_ID

        # Step 1: Normal occupancy via `occupancy/room1/count` & `occupancy/room1/density`
        logger.info("--- [SIM STEP 1] Normal Crowd Density ---")
        agent.route_topic_message(
            f"occupancy/{room}/count",
            json.dumps({"roomId": room, "totalCount": 14, "maxCapacity": 60}),
        )
        agent.route_topic_message(
            f"occupancy/{room}/density",
            json.dumps(
                {"roomId": room, "roomDensity": 0.12, "densityLevel": "LOW"}
            ),
        )
        state_1 = gpio.get_state()
        assert state_1["led"] == "GREEN" and state_1["buzzer"] is False

        # Step 2: Density approaching threshold (WARNING / HIGH) -> Yellow LED ON
        logger.info("--- [SIM STEP 2] Crowd Approaching Threshold (WARNING) ---")
        agent.route_topic_message(
            f"occupancy/{room}/count",
            json.dumps({"roomId": room, "totalCount": 50, "maxCapacity": 60}),
        )
        agent.route_topic_message(
            f"occupancy/{room}/density",
            json.dumps(
                {"roomId": room, "roomDensity": 0.41, "densityLevel": "HIGH"}
            ),
        )
        state_2 = gpio.get_state()
        assert state_2["led"] == "YELLOW" and state_2["buzzer"] is False

        # Step 3: Density exceeds critical limit -> Red LED ON + Buzzer PULSE ON
        logger.info("--- [SIM STEP 3] Critical Crowd Surge (RED LED + BUZZER) ---")
        agent.route_topic_message(
            f"occupancy/{room}/alerts",
            json.dumps(
                {
                    "roomId": room,
                    "severity": "CRITICAL",
                    "status": "ACTIVE",
                    "message": "Zone A density exceeded 0.55 people/m²",
                }
            ),
        )
        time.sleep(0.3)
        state_3 = gpio.get_state()
        assert state_3["led"] == "RED" and state_3["buzzer"] is True

        # Step 4: Operator sends SILENCE_BUZZER command via `occupancy/room1/device/command`
        logger.info("--- [SIM STEP 4] Operator Silences Buzzer via MQTT Command ---")
        agent.route_topic_message(
            f"occupancy/{room}/device/command",
            json.dumps({"action": "SILENCE_BUZZER"}),
        )
        state_4 = gpio.get_state()
        assert state_4["led"] == "RED" and state_4["buzzer"] is False

        # Step 5: Crowd disperses -> Alert Resolved & Normal Count -> Green LED ON
        logger.info("--- [SIM STEP 5] Crowd Disperses -> Return to Normal (GREEN) ---")
        agent.route_topic_message(
            f"occupancy/{room}/alerts",
            json.dumps({"roomId": room, "severity": "NONE", "status": "RESOLVED"}),
        )
        agent.route_topic_message(
            f"occupancy/{room}/count",
            json.dumps({"roomId": room, "totalCount": 18, "maxCapacity": 60}),
        )
        agent.route_topic_message(
            f"occupancy/{room}/density",
            json.dumps(
                {"roomId": room, "roomDensity": 0.15, "densityLevel": "LOW"}
            ),
        )
        state_5 = gpio.get_state()
        assert state_5["led"] == "GREEN" and state_5["buzzer"] is False

        # Step 6: Run Watchdog health verification
        assert watchdog.run_health_check_once() is True

    # Context manager exited -> verify all pins were cleaned up and driven LOW
    assert gpio.driver.read_pin(settings.GPIO_PIN_LED_GREEN) is False
    assert gpio.driver.read_pin(settings.GPIO_PIN_LED_YELLOW) is False
    assert gpio.driver.read_pin(settings.GPIO_PIN_LED_RED) is False
    assert gpio.driver.read_pin(settings.GPIO_PIN_BUZZER) is False
    logger.info("Simulation scenario completed and GPIO pins released cleanly.")
    return 0


def run_self_test() -> int:
    """Verify GPIO transitions and processor state machine."""
    return run_simulation_scenario()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart Indoor Occupancy - Raspberry Pi 4/5 IoT Edge Service"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run standalone interactive Simulation Mode scenario and exit",
    )
    parser.add_argument(
        "--force-sim-gpio",
        action="store_true",
        help="Run the MQTT service using Simulated GPIO driver",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run standalone hardware & processor verification and exit",
    )
    args = parser.parse_args()

    if args.self_test or args.simulate:
        return run_simulation_scenario()

    force_sim = bool(settings.SIMULATION_MODE or args.force_sim_gpio)

    gpio = GpioController(
        pin_led_green=settings.GPIO_PIN_LED_GREEN,
        pin_led_yellow=settings.GPIO_PIN_LED_YELLOW,
        pin_led_red=settings.GPIO_PIN_LED_RED,
        pin_buzzer=settings.GPIO_PIN_BUZZER,
        force_simulation=force_sim,
    )
    camera = CameraConnector(
        camera_source=settings.CAMERA_SOURCE,
        ai_service_url=settings.AI_SERVICE_URL,
        simulation_mode=gpio.is_simulation,
    )
    processor = OccupancyDataProcessor(settings=settings, gpio=gpio)
    agent = IotMqttAgent(
        settings=settings, gpio_controller=gpio, processor=processor
    )
    watchdog = ServiceWatchdog(
        settings=settings,
        gpio=gpio,
        processor=processor,
        mqtt_agent=agent,
        camera_connector=camera,
    )

    stop_requested = False

    def handle_signal(signum: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        logger.info(
            "Received OS signal %d -> initiating graceful shutdown & GPIO cleanup...",
            signum,
        )
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        cam_ok = camera.check_camera_available()
        logger.info("Camera interface check: available=%s", cam_ok)
        agent.start()
        watchdog.start()
        logger.info(
            "IoT Edge Service running (device='%s', room='%s', sim=%s). Press Ctrl+C to stop.",
            settings.IOT_DEVICE_ID,
            settings.IOT_ROOM_ID,
            gpio.is_simulation,
        )
        while not stop_requested:
            time.sleep(0.5)
    finally:
        watchdog.stop()
        agent.stop()
        gpio.cleanup()
        logger.info("IoT Edge Service stopped and GPIO pins released.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
