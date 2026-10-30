"""
Module 6: Crowd Alert Engine with Hysteresis & Sustain Duration (`crowd_alert.py`).

Algorithm Explanation (Hysteresis & Sustain Duration):
1. To avoid rapid alert flickering when crowd count or density fluctuates right around
   a threshold `T_trigger`, each rule defines:
   - `T_trigger`: threshold to enter violation state
   - `T_clear = T_trigger * (1.0 - hysteresis_ratio)`: lower threshold required to clear
     an already-active alert.
2. Sustain Timer (`sustain_sec`):
   - When `measured_value >= T_trigger`, a timer starts (`first_violated_ts`).
   - An alert is only emitted once the violation has been continuously sustained for
     at least `sustain_sec` seconds.
   - Once active, the alert remains active until `measured_value < T_clear`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from app.schemas.vision_schema import (
    AlertSeverity,
    EdgeCrowdAlert,
    ZoneTelemetry,
)


@dataclass
class HysteresisRuleState:
    key: str
    first_violated_ts: Optional[float] = None
    active_severity: Optional[AlertSeverity] = None
    triggered_at_iso: Optional[str] = None


class CrowdAlertEngine:
    """Evaluates room and zone crowd metrics with hysteresis and sustain duration."""

    def __init__(
        self,
        hysteresis_ratio: float = 0.10,
        sustain_sec: float = 2.0,
    ) -> None:
        self.hysteresis_ratio = min(0.5, max(0.0, hysteresis_ratio))
        self.sustain_sec = max(0.0, sustain_sec)
        self._states: Dict[str, HysteresisRuleState] = {}

    def reset(self) -> None:
        self._states.clear()

    def evaluate(
        self,
        room_id: str,
        room_name: str,
        total_count: int,
        room_max_capacity: int,
        room_density: float,
        room_warn_density: float,
        room_crit_density: float,
        zones: List[ZoneTelemetry],
        now_mono: Optional[float] = None,
    ) -> List[EdgeCrowdAlert]:
        now = now_mono if now_mono is not None else time.monotonic()
        active_alerts: List[EdgeCrowdAlert] = []

        # 1. Room-wide Occupancy Count check
        room_warn_count = max(1.0, round(room_max_capacity * 0.8))
        room_count_alert = self._evaluate_single_target(
            key=f"room:{room_id}:count",
            target_id=room_id,
            target_name=room_name,
            metric_type="PERSON_COUNT",
            measured=float(total_count),
            warn_thresh=room_warn_count,
            crit_thresh=float(room_max_capacity),
            unit="people",
            now=now,
        )
        if room_count_alert:
            active_alerts.append(room_count_alert)

        # 2. Room-wide Density check
        room_density_alert = self._evaluate_single_target(
            key=f"room:{room_id}:density",
            target_id=room_id,
            target_name=room_name,
            metric_type="DENSITY",
            measured=room_density,
            warn_thresh=room_warn_density,
            crit_thresh=room_crit_density,
            unit="people/m²",
            now=now,
        )
        if room_density_alert:
            active_alerts.append(room_density_alert)

        # 3. Per-Zone Count & Density checks
        for z in zones:
            z.alertActive = False
            z_warn_count = max(1.0, round(z.maxCapacity * 0.8))

            z_cnt_alert = self._evaluate_single_target(
                key=f"zone:{z.zoneId}:count",
                target_id=z.zoneId,
                target_name=f"{z.zoneName} ({z.zoneCode})",
                metric_type="PERSON_COUNT",
                measured=float(z.count),
                warn_thresh=z_warn_count,
                crit_thresh=float(z.maxCapacity),
                unit="people",
                now=now,
            )
            if z_cnt_alert:
                z.alertActive = True
                active_alerts.append(z_cnt_alert)

            z_den_alert = self._evaluate_single_target(
                key=f"zone:{z.zoneId}:density",
                target_id=z.zoneId,
                target_name=f"{z.zoneName} ({z.zoneCode})",
                metric_type="DENSITY",
                measured=z.density,
                warn_thresh=z.warningDensityThreshold,
                crit_thresh=z.criticalDensityThreshold,
                unit="people/m²",
                now=now,
            )
            if z_den_alert:
                z.alertActive = True
                active_alerts.append(z_den_alert)

        return active_alerts

    def _evaluate_single_target(
        self,
        key: str,
        target_id: str,
        target_name: str,
        metric_type: Literal["PERSON_COUNT", "DENSITY"],
        measured: float,
        warn_thresh: float,
        crit_thresh: float,
        unit: str,
        now: float,
    ) -> Optional[EdgeCrowdAlert]:
        state = self._states.get(key)
        if state is None:
            state = HysteresisRuleState(key=key)
            self._states[key] = state

        warn_clear = round(warn_thresh * (1.0 - self.hysteresis_ratio), 4)
        crit_clear = round(crit_thresh * (1.0 - self.hysteresis_ratio), 4)

        # Determine candidate severity applying hysteresis if already active
        candidate_severity: Optional[AlertSeverity] = None
        if state.active_severity == "CRITICAL":
            if measured >= crit_clear:
                candidate_severity = "CRITICAL"
            elif measured >= warn_clear:
                candidate_severity = "WARNING"
        elif state.active_severity == "WARNING":
            if measured >= crit_thresh:
                candidate_severity = "CRITICAL"
            elif measured >= warn_clear:
                candidate_severity = "WARNING"
        else:
            if measured >= crit_thresh:
                candidate_severity = "CRITICAL"
            elif measured >= warn_thresh:
                candidate_severity = "WARNING"

        if candidate_severity is None:
            state.first_violated_ts = None
            state.active_severity = None
            state.triggered_at_iso = None
            return None

        if state.first_violated_ts is None:
            state.first_violated_ts = now

        sustained_sec = round(max(0.0, now - state.first_violated_ts), 2)
        if sustained_sec < self.sustain_sec and state.active_severity is None:
            return None

        state.active_severity = candidate_severity
        if state.triggered_at_iso is None:
            state.triggered_at_iso = datetime.now(timezone.utc).isoformat()

        active_thresh = (
            crit_thresh if candidate_severity == "CRITICAL" else warn_thresh
        )
        clear_thresh = (
            crit_clear if candidate_severity == "CRITICAL" else warn_clear
        )

        return EdgeCrowdAlert(
            alertId=key,
            targetId=target_id,
            targetName=target_name,
            metricType=metric_type,
            severity=candidate_severity,
            measuredValue=round(measured, 3),
            thresholdValue=round(active_thresh, 3),
            clearThresholdValue=round(clear_thresh, 3),
            sustainedSec=sustained_sec,
            message=(
                f"[{candidate_severity}] {target_name}: {metric_type} = "
                f"{measured:.2f} {unit} (threshold {active_thresh:.2f} {unit}, "
                f"sustained {sustained_sec:.1f}s)"
            ),
            triggeredAt=state.triggered_at_iso,
        )
