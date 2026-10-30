"""
Historical Analytics & Short-Term Crowd Trend Forecasting Engine (Module 8).
Provides:
- Overview KPIs & Period-over-Period comparison
- Peak Hours identification (`00:00` - `23:00`)
- Hourly & Daily time-series bucket aggregation for Occupancy and Density
- Time-over-threshold computation
- Ordinary Least Squares (OLS) short-term occupancy & density forecasting
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Alert, DensityRecord, OccupancyRecord, Room
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    DailyBucketPoint,
    ForecastPoint,
    ForecastResponse,
    HourlyBucketPoint,
    PeakHourEntry,
)


class AnalyticsEngine:
    """Computes historical statistics, peak hours, period comparisons, and forecasts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_overview(
        self, room: Room, hours: int = 24
    ) -> AnalyticsOverviewResponse:
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(hours=hours)
        prev_start = current_start - timedelta(hours=hours)

        current_records = (
            self.db.query(OccupancyRecord)
            .filter(
                OccupancyRecord.room_id == room.id,
                OccupancyRecord.recorded_at >= current_start,
            )
            .order_by(OccupancyRecord.recorded_at.asc())
            .all()
        )
        prev_records = (
            self.db.query(OccupancyRecord)
            .filter(
                OccupancyRecord.room_id == room.id,
                OccupancyRecord.recorded_at >= prev_start,
                OccupancyRecord.recorded_at < current_start,
            )
            .all()
        )

        total_samples = len(current_records)
        if total_samples > 0:
            avg_occ = round(
                sum(r.total_count for r in current_records) / total_samples, 2
            )
            peak_occ = max(r.total_count for r in current_records)
            avg_den = round(
                sum(r.overall_density for r in current_records) / total_samples, 4
            )
            peak_den = round(
                max(r.overall_density for r in current_records), 4
            )
            over_samples = sum(
                1
                for r in current_records
                if r.room_status in ("WARNING", "CRITICAL")
                or r.capacity_ratio >= room.warning_threshold_ratio
                or r.overall_density >= room.critical_density_per_sqm
            )
        else:
            avg_occ = 0.0
            peak_occ = 0
            avg_den = 0.0
            peak_den = 0.0
            over_samples = 0

        sample_interval = max(1, settings.OCCUPANCY_LOG_INTERVAL_SEC)
        over_seconds = float(over_samples * sample_interval)
        over_minutes = round(over_seconds / 60.0, 2)
        over_ratio_pct = (
            round((over_samples / total_samples) * 100.0, 2)
            if total_samples > 0
            else 0.0
        )

        # Period-over-Period comparison
        prev_samples = len(prev_records)
        if prev_samples > 0:
            prev_avg_occ = round(
                sum(r.total_count for r in prev_records) / prev_samples, 2
            )
            prev_avg_den = round(
                sum(r.overall_density for r in prev_records) / prev_samples, 4
            )
        else:
            prev_avg_occ = 0.0
            prev_avg_den = 0.0

        occ_delta_pct = (
            round(((avg_occ - prev_avg_occ) / prev_avg_occ) * 100.0, 2)
            if prev_avg_occ > 0
            else 0.0
        )
        den_delta_pct = (
            round(((avg_den - prev_avg_den) / prev_avg_den) * 100.0, 2)
            if prev_avg_den > 0
            else 0.0
        )

        active_alerts = (
            self.db.query(Alert)
            .filter(Alert.room_id == room.id, Alert.is_resolved.is_(False))
            .count()
        )

        return AnalyticsOverviewResponse(
            room_id=room.id,
            room_code=room.code,
            room_name=room.name,
            period_hours=hours,
            total_samples=total_samples,
            average_occupancy=avg_occ,
            peak_occupancy=peak_occ,
            average_density_per_sqm=avg_den,
            peak_density_per_sqm=peak_den,
            time_over_threshold_seconds=over_seconds,
            time_over_threshold_minutes=over_minutes,
            over_threshold_ratio_pct=over_ratio_pct,
            active_alerts_count=active_alerts,
            period_comparison={
                "previous_period_samples": prev_samples,
                "previous_average_occupancy": prev_avg_occ,
                "previous_average_density": prev_avg_den,
                "occupancy_change_pct": occ_delta_pct,
                "density_change_pct": den_delta_pct,
            },
        )

    def get_peak_hours(
        self, room: Room, days: int = 7
    ) -> List[PeakHourEntry]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        records = (
            self.db.query(OccupancyRecord)
            .filter(
                OccupancyRecord.room_id == room.id,
                OccupancyRecord.recorded_at >= since,
            )
            .all()
        )

        buckets: Dict[int, List[OccupancyRecord]] = defaultdict(list)
        for rec in records:
            hr = rec.recorded_at.hour if rec.recorded_at else 0
            buckets[hr].append(rec)

        results: List[PeakHourEntry] = []
        for hr in sorted(buckets.keys()):
            items = buckets[hr]
            avg_c = round(sum(x.total_count for x in items) / len(items), 2)
            max_c = max(x.total_count for x in items)
            avg_d = round(sum(x.overall_density for x in items) / len(items), 4)
            results.append(
                PeakHourEntry(
                    hour_of_day=hr,
                    label=f"{hr:02d}:00 - {hr:02d}:59",
                    avg_count=avg_c,
                    max_count=max_c,
                    avg_density=avg_d,
                    sample_count=len(items),
                    hourOfDay=hr,
                    avgCount=avg_c,
                    maxCount=max_c,
                )
            )
        return results

    def get_hourly_series(
        self, room: Room, hours: int = 24
    ) -> List[HourlyBucketPoint]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        records = (
            self.db.query(OccupancyRecord)
            .filter(
                OccupancyRecord.room_id == room.id,
                OccupancyRecord.recorded_at >= since,
            )
            .order_by(OccupancyRecord.recorded_at.asc())
            .all()
        )
        grouped: Dict[str, List[OccupancyRecord]] = defaultdict(list)
        for rec in records:
            key = rec.recorded_at.strftime("%Y-%m-%d %H:00")
            grouped[key].append(rec)

        points: List[HourlyBucketPoint] = []
        for bucket_key in sorted(grouped.keys()):
            items = grouped[bucket_key]
            hr = items[0].recorded_at.hour
            points.append(
                HourlyBucketPoint(
                    hour_bucket=bucket_key,
                    hour_of_day=hr,
                    avg_occupancy=round(
                        sum(x.total_count for x in items) / len(items), 2
                    ),
                    peak_occupancy=max(x.total_count for x in items),
                    avg_density=round(
                        sum(x.overall_density for x in items) / len(items), 4
                    ),
                    peak_density=round(
                        max(x.overall_density for x in items), 4
                    ),
                    sample_count=len(items),
                )
            )
        return points

    def get_daily_series(
        self, room: Room, days: int = 7
    ) -> List[DailyBucketPoint]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        records = (
            self.db.query(OccupancyRecord)
            .filter(
                OccupancyRecord.room_id == room.id,
                OccupancyRecord.recorded_at >= since,
            )
            .order_by(OccupancyRecord.recorded_at.asc())
            .all()
        )
        grouped: Dict[str, List[OccupancyRecord]] = defaultdict(list)
        for rec in records:
            key = rec.recorded_at.strftime("%Y-%m-%d")
            grouped[key].append(rec)

        sample_interval = max(1, settings.OCCUPANCY_LOG_INTERVAL_SEC)
        points: List[DailyBucketPoint] = []
        for date_key in sorted(grouped.keys()):
            items = grouped[date_key]
            over_cnt = sum(
                1
                for r in items
                if r.room_status in ("WARNING", "CRITICAL")
                or r.capacity_ratio >= room.warning_threshold_ratio
                or r.overall_density >= room.critical_density_per_sqm
            )
            points.append(
                DailyBucketPoint(
                    date_bucket=date_key,
                    avg_occupancy=round(
                        sum(x.total_count for x in items) / len(items), 2
                    ),
                    peak_occupancy=max(x.total_count for x in items),
                    total_in=max((x.in_count for x in items), default=0),
                    total_out=max((x.out_count for x in items), default=0),
                    avg_density=round(
                        sum(x.overall_density for x in items) / len(items), 4
                    ),
                    peak_density=round(
                        max(x.overall_density for x in items), 4
                    ),
                    over_threshold_samples=over_cnt,
                    over_threshold_minutes=round(
                        (over_cnt * sample_interval) / 60.0, 2
                    ),
                )
            )
        return points

    def get_forecast(
        self, room: Room, horizon_minutes: int = 30
    ) -> ForecastResponse:
        """
        Short-term crowd density forecasting using Ordinary Least Squares (OLS)
        linear regression over recent occupancy telemetry.
        """
        horizon_minutes = max(5, min(horizon_minutes, 120))
        recent = (
            self.db.query(OccupancyRecord)
            .filter(OccupancyRecord.room_id == room.id)
            .order_by(OccupancyRecord.recorded_at.desc())
            .limit(120)
            .all()
        )
        recent = list(reversed(recent))

        if len(recent) < 2:
            base_count = recent[0].total_count if recent else 0
            area = max(1.0, room.area_sqm)
            preds: List[ForecastPoint] = []
            for step in range(5, horizon_minutes + 1, 5):
                den = round(base_count / area, 4)
                preds.append(
                    ForecastPoint(
                        minute_offset=step,
                        predicted_count=base_count,
                        predicted_density=den,
                        confidence_low=max(0, base_count - 1),
                        confidence_high=base_count + 1,
                        minuteOffset=step,
                        predictedCount=base_count,
                        predictedDensity=den,
                        confidenceLow=max(0, base_count - 1),
                        confidenceHigh=base_count + 1,
                    )
                )
            return ForecastResponse(
                room_id=room.id,
                horizon_minutes=horizon_minutes,
                slope_per_minute=0.0,
                r_squared=0.0,
                trend="STABLE",
                predictions=preds,
                roomId=room.id,
                horizonMinutes=horizon_minutes,
                slopePerMinute=0.0,
                rSquared=0.0,
            )

        t0 = recent[0].recorded_at
        xs = [
            max(0.0, (r.recorded_at - t0).total_seconds() / 60.0)
            for r in recent
        ]
        # If all timestamps are nearly identical (e.g., unit test insertion), space by sample index
        if max(xs) - min(xs) < 1e-6:
            xs = [float(i) for i in range(len(recent))]

        ys = [float(r.total_count) for r in recent]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        ss_xx = sum((x - mean_x) ** 2 for x in xs)
        ss_yy = sum((y - mean_y) ** 2 for y in ys)
        ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

        slope = ss_xy / ss_xx if ss_xx > 1e-9 else 0.0
        intercept = mean_y - slope * mean_x
        r_squared = (
            (ss_xy**2) / (ss_xx * ss_yy)
            if (ss_xx > 1e-9 and ss_yy > 1e-9)
            else 0.0
        )

        residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
        std_err = (
            math.sqrt(sum(res**2 for res in residuals) / max(1, n - 2))
            if n > 2
            else 1.0
        )

        last_x = xs[-1]
        area = max(1.0, room.area_sqm)
        predictions: List[ForecastPoint] = []
        for step in range(5, horizon_minutes + 1, 5):
            future_x = last_x + step
            raw_pred = intercept + slope * future_x
            pred_count = max(0, min(room.max_capacity * 2, int(round(raw_pred))))
            margin = max(1, int(round(1.96 * std_err * math.sqrt(1 + step / 30.0))))
            low = max(0, pred_count - margin)
            high = pred_count + margin
            den = round(pred_count / area, 4)

            predictions.append(
                ForecastPoint(
                    minute_offset=step,
                    predicted_count=pred_count,
                    predicted_density=den,
                    confidence_low=low,
                    confidence_high=high,
                    minuteOffset=step,
                    predictedCount=pred_count,
                    predictedDensity=den,
                    confidenceLow=low,
                    confidenceHigh=high,
                )
            )

        if slope > 0.15:
            trend = "INCREASING"
        elif slope < -0.15:
            trend = "DECREASING"
        else:
            trend = "STABLE"

        return ForecastResponse(
            room_id=room.id,
            horizon_minutes=horizon_minutes,
            slope_per_minute=round(slope, 4),
            r_squared=round(r_squared, 4),
            trend=trend,
            predictions=predictions,
            roomId=room.id,
            horizonMinutes=horizon_minutes,
            slopePerMinute=round(slope, 4),
            rSquared=round(r_squared, 4),
        )
