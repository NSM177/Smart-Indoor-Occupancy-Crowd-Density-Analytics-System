"""Environment-driven settings for the AI Computer Vision Engine."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class AiServiceSettings(BaseSettings):
    """Pydantic settings loaded from .env or environment variables."""

    AI_SERVICE_HOST: str = "0.0.0.0"
    AI_SERVICE_PORT: int = 8000
    BACKEND_INTERNAL_URL: str = "http://localhost:4000/api/v1"

    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""

    # Video / Camera Input Source ("0", "picamera", RTSP URL, or path to .mp4 file)
    CAMERA_SOURCE: str = "0"
    FRAME_WIDTH: int = 1280
    FRAME_HEIGHT: int = 720
    TARGET_FPS: int = 15

    # Performance Optimization for Raspberry Pi 4/5
    INFERENCE_WIDTH: int = 640
    INFERENCE_HEIGHT: int = 384
    FRAME_SKIP: int = 1  # 1 = infer every frame, 2 = infer every 2nd frame, etc.

    # YOLO + ByteTrack Configuration
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.35
    YOLO_LOW_CONFIDENCE_THRESHOLD: float = 0.15
    YOLO_IOU_THRESHOLD: float = 0.45
    BYTETRACK_MATCH_THRESH: float = 0.25
    BYTETRACK_TRACK_BUFFER: int = 30

    # Zone JSON & Heatmap Configuration
    ZONES_CONFIG_PATH: str = str(BASE_DIR / "config" / "zones.json")
    HEATMAP_SAVE_DIR: str = str(BASE_DIR / "outputs" / "heatmaps")
    HEATMAP_GRID_WIDTH: int = 64
    HEATMAP_GRID_HEIGHT: int = 36
    HEATMAP_DECAY_FACTOR: float = 0.96

    # Crowd Alert Hysteresis & Sustain Configuration
    ALERT_HYSTERESIS_RATIO: float = 0.10
    ALERT_SUSTAIN_SEC: float = 2.0
    ALERT_COOLDOWN_SEC: float = 15.0

    TELEMETRY_PUBLISH_INTERVAL_SEC: float = 1.0

    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env"),
            str(BASE_DIR.parent / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = AiServiceSettings()
