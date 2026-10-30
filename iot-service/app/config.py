"""Configuration management for the Raspberry Pi 4/5 IoT Edge Service."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class IotSettings(BaseSettings):
    """Environment-driven settings for the Raspberry Pi IoT Module."""

    # MQTT Broker Settings
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_KEEPALIVE_SEC: int = 30
    MQTT_RECONNECT_MIN_SEC: int = 1
    MQTT_RECONNECT_MAX_SEC: int = 30

    # Device & Room Identification
    IOT_DEVICE_ID: str = "RPI_NODE_01"
    IOT_DEVICE_NAME: str = "Raspberry Pi 5 Edge Controller"
    IOT_ROOM_ID: str = "room1"

    # Approved BCM GPIO Pin Mapping (Raspberry Pi 4/5 40-Pin Header J8)
    GPIO_PIN_LED_GREEN: int = 17   # Physical Pin 11
    GPIO_PIN_LED_YELLOW: int = 27  # Physical Pin 13
    GPIO_PIN_LED_RED: int = 22     # Physical Pin 15
    GPIO_PIN_BUZZER: int = 23      # Physical Pin 16

    # Simulation Mode
    SIMULATION_MODE: bool = False

    # Thresholds & Buzzer Safety Timer
    ROOM_MAX_CAPACITY: int = 60
    WARNING_OCCUPANCY_RATIO: float = 0.80
    WARNING_DENSITY_THRESHOLD: float = 0.35
    CRITICAL_DENSITY_THRESHOLD: float = 0.50
    BUZZER_MAX_DURATION_SEC: int = 15

    # Camera & AI Service Integration
    CAMERA_ENABLED: bool = True
    CAMERA_SOURCE: str = "0"
    CAMERA_STREAM_PORT: int = 8081
    AI_SERVICE_URL: str = "http://localhost:8000"

    # Heartbeat, Watchdog & Logging
    IOT_HEARTBEAT_INTERVAL_SEC: int = 10
    WATCHDOG_CHECK_INTERVAL_SEC: int = 5
    TELEMETRY_STALE_TIMEOUT_SEC: int = 60
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = str(BASE_DIR / "logs" / "iot_device.log")

    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env"),
            str(BASE_DIR.parent / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = IotSettings()
