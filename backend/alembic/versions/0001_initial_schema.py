"""Initial 9-table schema for Smart Indoor Occupancy & Crowd Density Analytics System.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-10-30 13:00:00
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(128), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column("max_capacity", sa.Integer(), nullable=False),
        sa.Column("warning_threshold_ratio", sa.Float(), nullable=False),
        sa.Column("critical_density_per_sqm", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "zones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("polygon_coordinates", sa.JSON(), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column("max_capacity", sa.Integer(), nullable=False),
        sa.Column("warning_density", sa.Float(), nullable=False),
        sa.Column("critical_density", sa.Float(), nullable=False),
        sa.Column("color_hex", sa.String(9), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "code", name="uq_zones_room_code"),
    )
    op.create_index("idx_zones_room_id", "zones", ["room_id"])

    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("device_type", sa.String(32), nullable=False),
        sa.Column("stream_url", sa.String(256), nullable=True),
        sa.Column("resolution_width", sa.Integer(), nullable=False),
        sa.Column("resolution_height", sa.Integer(), nullable=False),
        sa.Column("fps_target", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("led_state", sa.String(16), nullable=False),
        sa.Column("buzzer_active", sa.Boolean(), nullable=False),
        sa.Column("auto_mode", sa.Boolean(), nullable=False),
        sa.Column("gpio_mode", sa.String(24), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("firmware_version", sa.String(32), nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_devices_room_status", "devices", ["room_id", "status"])

    op.create_table(
        "occupancy_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("in_count", sa.Integer(), nullable=False),
        sa.Column("out_count", sa.Integer(), nullable=False),
        sa.Column("overall_density", sa.Float(), nullable=False),
        sa.Column("capacity_ratio", sa.Float(), nullable=False),
        sa.Column("room_status", sa.String(24), nullable=False),
        sa.Column("inference_fps", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_occupancy_room_recorded", "occupancy_records", ["room_id", "recorded_at"])

    op.create_table(
        "density_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", sa.String(36), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_count", sa.Integer(), nullable=False),
        sa.Column("density_per_sqm", sa.Float(), nullable=False),
        sa.Column("capacity_ratio", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_density_room_zone_recorded", "density_records", ["room_id", "zone_id", "recorded_at"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("room_id", sa.String(36), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", sa.String(36), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("person_count", sa.Integer(), nullable=False),
        sa.Column("density_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_alerts_room_severity_status", "alerts", ["room_id", "severity", "is_resolved"])
    op.create_index("idx_alerts_triggered_at", "alerts", ["triggered_at"])

    op.create_table(
        "device_status_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("led_state", sa.String(16), nullable=False),
        sa.Column("buzzer_active", sa.Boolean(), nullable=False),
        sa.Column("auto_mode", sa.Boolean(), nullable=False),
        sa.Column("person_count", sa.Integer(), nullable=False),
        sa.Column("density", sa.Float(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_device_status_logs_device_logged", "device_status_logs", ["device_id", "logged_at"])

    op.create_table(
        "system_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_system_events_source_created", "system_events", ["source", "created_at"])


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("device_status_logs")
    op.drop_table("alerts")
    op.drop_table("density_records")
    op.drop_table("occupancy_records")
    op.drop_table("devices")
    op.drop_table("zones")
    op.drop_table("rooms")
    op.drop_table("users")
