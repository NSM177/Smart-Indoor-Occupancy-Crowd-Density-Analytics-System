"""Pydantic v2 schemas for Historical Analytics, Peak Hours & Forecasting (Module 8)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class HourlyBucketPoint(BaseModel):
    hour_bucket: str
    hour_of_day: int
    avg_occupancy: float
    peak_occupancy: int
    avg_density: float
    peak_density: float
    sample_count: int


class DailyBucketPoint(BaseModel):
    date_bucket: str
    avg_occupancy: float
    peak_occupancy: int
    total_in: int
    total_out: int
    avg_density: float
    peak_density: float
    over_threshold_samples: int
    over_threshold_minutes: float


class AnalyticsOverviewResponse(BaseModel):
    room_id: str
    room_code: str
    room_name: str
    period_hours: int
    total_samples: int
    average_occupancy: float
    peak_occupancy: int
    average_density_per_sqm: float
    peak_density_per_sqm: float
    time_over_threshold_seconds: float
    time_over_threshold_minutes: float
    over_threshold_ratio_pct: float
    active_alerts_count: int
    period_comparison: Dict[str, Any]


class PeakHourEntry(BaseModel):
    hour_of_day: int
    label: str
    avg_count: float
    max_count: int
    avg_density: float
    sample_count: int

    # CamelCase compatibility for Frontend
    hourOfDay: Optional[int] = None
    avgCount: Optional[float] = None
    maxCount: Optional[int] = None


class ForecastPoint(BaseModel):
    minute_offset: int
    predicted_count: int
    predicted_density: float
    confidence_low: int
    confidence_high: int

    # CamelCase compatibility for Frontend
    minuteOffset: Optional[int] = None
    predictedCount: Optional[int] = None
    predictedDensity: Optional[float] = None
    confidenceLow: Optional[int] = None
    confidenceHigh: Optional[int] = None


class ForecastResponse(BaseModel):
    room_id: str
    horizon_minutes: int
    slope_per_minute: float
    r_squared: float
    trend: str
    predictions: List[ForecastPoint]

    # CamelCase compatibility for Frontend
    roomId: Optional[str] = None
    horizonMinutes: Optional[int] = None
    slopePerMinute: Optional[float] = None
    rSquared: Optional[float] = None
