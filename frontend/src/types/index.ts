/**
 * Strict TypeScript Domain Interfaces for:
 * Smart Indoor Occupancy & Crowd Density Analytics System
 * Aligned 100% with the Python FastAPI Backend (`/api/v1/*`) & WebSocket (`/ws/realtime`).
 */

export type UserRole = 'ADMIN' | 'OPERATOR';
export type SeverityLevel = 'NORMAL' | 'WARNING' | 'CRITICAL';
export type DeviceStatusType = 'ONLINE' | 'OFFLINE';
export type LedColor = 'GREEN' | 'YELLOW' | 'RED' | 'OFF';
export type WsConnectionStatus =
  | 'CONNECTING'
  | 'CONNECTED'
  | 'RECONNECTING'
  | 'DISCONNECTED';

export interface Point2D {
  x: number;
  y: number;
}

// ============================================================================
// Module 1: Authentication & Users
// ============================================================================
export interface UserProfile {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

export interface CreateUserPayload {
  username: string;
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
}

// ============================================================================
// Module 2 & 3: Rooms & Polygon Zones
// ============================================================================
export interface ZoneEntity {
  id: string;
  room_id: string;
  name: string;
  code: string;
  polygon_coordinates: Point2D[];
  area_sqm: number;
  max_capacity: number;
  warning_density: number;
  critical_density: number;
  color_hex: string;
  created_at: string;
  updated_at: string;
}

export interface RoomEntity {
  id: string;
  code: string;
  name: string;
  description: string | null;
  area_sqm: number;
  max_capacity: number;
  warning_threshold_ratio: number;
  critical_density_per_sqm: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  zones: ZoneEntity[];
}

export interface RoomCreatePayload {
  code?: string;
  name: string;
  description?: string;
  area_sqm: number;
  max_capacity: number;
  warning_threshold_ratio: number;
  critical_density_per_sqm: number;
  is_active?: boolean;
}

export interface RoomUpdatePayload {
  code?: string;
  name?: string;
  description?: string;
  area_sqm?: number;
  max_capacity?: number;
  warning_threshold_ratio?: number;
  critical_density_per_sqm?: number;
  is_active?: boolean;
}

export interface ZoneCreatePayload {
  room_id?: string;
  name: string;
  code: string;
  polygon_coordinates: Point2D[];
  area_sqm: number;
  max_capacity: number;
  warning_density: number;
  critical_density: number;
  color_hex: string;
}

export interface ZoneUpdatePayload {
  name?: string;
  code?: string;
  polygon_coordinates?: Point2D[];
  area_sqm?: number;
  max_capacity?: number;
  warning_density?: number;
  critical_density?: number;
  color_hex?: string;
}

// ============================================================================
// Module 4: Occupancy Management
// ============================================================================
export interface OccupancyCurrent {
  room_id: string;
  room_code: string;
  room_name: string;
  current_count: number;
  in_count: number;
  out_count: number;
  max_capacity: number;
  capacity_ratio: number;
  overall_density: number;
  room_status: SeverityLevel;
  inference_fps: number | null;
  updated_at: string;
}

export interface OccupancyRecord {
  id: number;
  room_id: string;
  device_id: string | null;
  total_count: number;
  in_count: number;
  out_count: number;
  overall_density: number;
  capacity_ratio: number;
  room_status: SeverityLevel;
  inference_fps: number | null;
  recorded_at: string;
}

// ============================================================================
// Module 5: Density Analytics
// ============================================================================
export interface ZoneDensitySnapshot {
  zone_id: string;
  zone_code: string;
  zone_name: string;
  person_count: number;
  area_sqm: number;
  max_capacity: number;
  density_per_sqm: number;
  capacity_ratio: number;
  utilization_pct: number;
  severity: SeverityLevel;
}

export interface RoomDensityCurrent {
  room_id: string;
  room_code: string;
  room_name: string;
  total_count: number;
  area_sqm: number;
  max_capacity: number;
  overall_density_per_sqm: number;
  capacity_utilization_pct: number;
  room_status: SeverityLevel;
  busiest_zone: ZoneDensitySnapshot | null;
  zones: ZoneDensitySnapshot[];
  updated_at: string;
}

export interface DensityRecord {
  id: number;
  room_id: string;
  zone_id: string;
  zone_code: string | null;
  zone_name: string | null;
  person_count: number;
  density_per_sqm: number;
  capacity_ratio: number;
  severity: SeverityLevel;
  recorded_at: string;
}

// ============================================================================
// Module 6: Alert Management
// ============================================================================
export interface AlertEntity {
  id: string;
  room_id: string;
  zone_id: string | null;
  alert_type: string;
  severity: SeverityLevel;
  message: string;
  person_count: number;
  density_value: number;
  threshold_value: number;
  is_acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  is_resolved: boolean;
  resolved_at: string | null;
  triggered_at: string;
}

// ============================================================================
// Module 7: Device Management
// ============================================================================
export interface DeviceEntity {
  id: string;
  room_id: string;
  device_code: string;
  name: string;
  device_type: string;
  stream_url: string | null;
  resolution_width: number;
  resolution_height: number;
  fps_target: number;
  status: DeviceStatusType;
  is_online: boolean;
  led_state: LedColor;
  buzzer_active: boolean;
  auto_mode: boolean;
  gpio_mode: string;
  ip_address: string | null;
  firmware_version: string;
  last_heartbeat: string | null;
}

export interface DeviceCommandPayload {
  led_state?: LedColor;
  buzzer_active?: boolean;
  auto_mode?: boolean;
  reset_counters?: boolean;
}

// ============================================================================
// Module 8: Historical Analytics, Peak Hours & Forecasting
// ============================================================================
export interface AnalyticsOverview {
  room_id: string;
  room_code: string;
  room_name: string;
  period_hours: number;
  total_samples: number;
  average_occupancy: number;
  peak_occupancy: number;
  average_density_per_sqm: number;
  peak_density_per_sqm: number;
  time_over_threshold_seconds: number;
  time_over_threshold_minutes: number;
  over_threshold_ratio_pct: number;
  active_alerts_count: number;
  period_comparison: {
    previous_period_samples: number;
    previous_average_occupancy: number;
    previous_average_density: number;
    occupancy_change_pct: number;
    density_change_pct: number;
  };
}

export interface PeakHourItem {
  hour_of_day: number;
  label: string;
  avg_count: number;
  max_count: number;
  avg_density: number;
  sample_count: number;
}

export interface HourlyBucketPoint {
  hour_bucket: string;
  hour_of_day: number;
  avg_occupancy: number;
  peak_occupancy: number;
  avg_density: number;
  peak_density: number;
  sample_count: number;
}

export interface DailyBucketPoint {
  date_bucket: string;
  avg_occupancy: number;
  peak_occupancy: number;
  total_in: number;
  total_out: number;
  avg_density: number;
  peak_density: number;
  over_threshold_samples: number;
  over_threshold_minutes: number;
}

export interface ForecastPoint {
  minute_offset: number;
  predicted_count: number;
  predicted_density: number;
  confidence_low: number;
  confidence_high: number;
}

export interface ForecastData {
  room_id: string;
  horizon_minutes: number;
  slope_per_minute: number;
  r_squared: number;
  trend: 'INCREASING' | 'DECREASING' | 'STABLE';
  predictions: ForecastPoint[];
}

export interface AiEngineRealtimeAnalytics {
  room_id: string;
  timestamp: string;
  frame_index: number;
  current_count: number;
  in_count: number;
  out_count: number;
  overall_density: number;
  capacity_ratio: number;
  alert_level: SeverityLevel;
  performance: {
    fps: number;
    inference_ms: number;
    processing_ms: number;
    frame_skip: number;
  };
  zones: Array<{
    zone_code: string;
    zone_name: string;
    count: number;
    area_sqm: number;
    max_capacity: number;
    density_per_sqm: number;
    capacity_ratio: number;
    severity: SeverityLevel;
  }>;
  heatmap_grid?: number[][];
}

// ============================================================================
// WebSocket Event Envelope
// ============================================================================
export type WsEventType =
  | 'connected'
  | 'pong'
  | 'subscribed'
  | 'occupancy.updated'
  | 'density.updated'
  | 'zone.updated'
  | 'alert.created'
  | 'device.status_changed';

export interface WsEnvelope<T = Record<string, unknown>> {
  event: WsEventType;
  room_id?: string | null;
  timestamp: string;
  data?: T;
  client_id?: string;
  initial_state?: Record<string, unknown>;
}
