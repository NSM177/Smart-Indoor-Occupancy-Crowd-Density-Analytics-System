"""Pydantic v2 schemas for IoT & Camera Device Management (Module 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class DeviceCommandRequest(BaseModel):
    led_state: Optional[Literal["GREEN", "YELLOW", "RED", "OFF"]] = Field(
        default=None, alias="ledState"
    )
    buzzer_active: Optional[bool] = Field(default=None, alias="buzzerActive")
    auto_mode: Optional[bool] = Field(default=None, alias="autoMode")
    reset_counters: Optional[bool] = Field(default=None, alias="resetCounters")

    model_config = ConfigDict(populate_by_name=True)


class DeviceResponse(BaseModel):
    id: str
    room_id: str
    device_code: str
    name: str
    device_type: str
    stream_url: Optional[str] = None
    resolution_width: int
    resolution_height: int
    fps_target: int
    status: str
    is_online: bool
    led_state: str
    buzzer_active: bool
    auto_mode: bool
    gpio_mode: str
    ip_address: Optional[str] = None
    firmware_version: str
    last_heartbeat: Optional[datetime] = None

    # CamelCase compatibility for Frontend
    deviceId: Optional[str] = None
    roomId: Optional[str] = None
    ledState: Optional[str] = None
    buzzerActive: Optional[bool] = None
    autoMode: Optional[bool] = None
    gpioMode: Optional[str] = None
    lastSeen: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm_device(cls, dev, is_online: Optional[bool] = None) -> "DeviceResponse":
        online = is_online if is_online is not None else (dev.status == "ONLINE")
        status_str = "ONLINE" if online else "OFFLINE"
        last_seen_iso = dev.last_heartbeat.isoformat() if dev.last_heartbeat else None
        return cls(
            id=dev.id,
            room_id=dev.room_id,
            device_code=dev.device_code,
            name=dev.name,
            device_type=dev.device_type,
            stream_url=dev.stream_url,
            resolution_width=dev.resolution_width,
            resolution_height=dev.resolution_height,
            fps_target=dev.fps_target,
            status=status_str,
            is_online=online,
            led_state=dev.led_state,
            buzzer_active=dev.buzzer_active,
            auto_mode=dev.auto_mode,
            gpio_mode=dev.gpio_mode,
            ip_address=dev.ip_address,
            firmware_version=dev.firmware_version,
            last_heartbeat=dev.last_heartbeat,
            deviceId=dev.device_code,
            roomId=dev.room_id,
            ledState=dev.led_state,
            buzzerActive=dev.buzzer_active,
            autoMode=dev.auto_mode,
            gpioMode=dev.gpio_mode,
            lastSeen=last_seen_iso,
        )
