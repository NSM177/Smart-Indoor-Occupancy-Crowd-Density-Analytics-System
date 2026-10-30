"""Environment-driven settings for the Python FastAPI Backend."""

from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class BackendSettings(BaseSettings):
    """Pydantic v2 configuration loaded from .env or environment variables."""

    APP_NAME: str = "Smart Indoor Occupancy & Crowd Density Analytics Backend"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 4000
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # PostgreSQL Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "occupancy_admin"
    POSTGRES_PASSWORD: str = "occupancy_secret_pwd"
    POSTGRES_DB: str = "smart_occupancy_db"
    DATABASE_URL: str = ""

    # JWT Authentication & RBAC
    JWT_SECRET_KEY: str = "smart_occupancy_super_secret_jwt_key_2026_change_in_prod"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@123"
    DEFAULT_OPERATOR_USERNAME: str = "operator"
    DEFAULT_OPERATOR_PASSWORD: str = "Operator@123"

    # Eclipse Mosquitto MQTT Broker
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_CLIENT_ID_PREFIX: str = "smart_occupancy_py_backend"

    # External AI Service & Persistence Intervals
    AI_SERVICE_URL: str = "http://localhost:8000"
    OCCUPANCY_LOG_INTERVAL_SEC: int = 5
    DEVICE_OFFLINE_TIMEOUT_SEC: int = 35

    # Initial Room Seed Configuration
    INITIAL_ROOM_CODE: str = "room1"
    INITIAL_ROOM_NAME: str = "Main Conference & Exhibition Hall"
    INITIAL_ROOM_AREA_SQM: float = 120.0
    INITIAL_ROOM_MAX_CAPACITY: int = 60
    INITIAL_CAMERA_NAME: str = "Primary Overhead Camera 01"
    INITIAL_CAMERA_STREAM_URL: str = "0"
    IOT_DEVICE_ID: str = "RPI_NODE_01"

    model_config = SettingsConfigDict(
        env_file=(
            str(BASE_DIR / ".env"),
            str(BASE_DIR.parent / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.DATABASE_URL.strip():
            return self.DATABASE_URL.strip()
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origin_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [
            item.strip()
            for item in self.CORS_ORIGINS.split(",")
            if item.strip()
        ]


settings = BackendSettings()
