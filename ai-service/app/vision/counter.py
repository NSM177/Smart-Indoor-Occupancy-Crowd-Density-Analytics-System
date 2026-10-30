"""
Module 3: People Counting & Virtual Line Crossing Engine (`counter.py`).

Algorithm Explanation (Virtual Line Crossing & State Machine):
1. Given a Virtual Line segment AB defined by `A = (x1, y1)` and `B = (x2, y2)`
   and a tracked person's foot movement segment PQ from `P = trajectory[-2]` to `Q = trajectory[-1]`:
2. Two segments AB and PQ intersect if and only if:
   - Points P and Q lie on opposite sides of line AB: `ccw(A, B, P) != ccw(A, B, Q)`
   - Points A and B lie on opposite sides of segment PQ: `ccw(P, Q, A) != ccw(P, Q, B)`
3. Crossing Direction (`IN` vs `OUT`):
   - Computed from the 2D vector cross product `(B - A) x (Q - P)` and the configured
     `inDirection` (`DOWN`, `UP`, `LEFT`, `RIGHT`).
4. Anti-Double-Counting State Machine:
   - For each `(line_id, track_id)`, we record the last counted direction (`IN` or `OUT`)
     and timestamp. A track cannot trigger the same direction twice in a row without first
     crossing in the opposite direction or waiting past a minimum debounce interval.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Set, Tuple

from app.schemas.vision_schema import (
    LineCrossingStats,
    TrackedPerson,
    VirtualLineConfig,
)
from app.vision.tracker import ByteTracker

CrossDirection = Literal["IN", "OUT"]


def _ccw(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> float:
    """2D cross product (p2 - p1) x (p3 - p1)."""
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (
        p3[0] - p1[0]
    )


def segments_intersect(
    a: Tuple[float, float],
    b: Tuple[float, float],
    p: Tuple[float, float],
    q: Tuple[float, float],
) -> bool:
    """Return True if segment AB and segment PQ intersect."""
    c1 = _ccw(a, b, p)
    c2 = _ccw(a, b, q)
    c3 = _ccw(p, q, a)
    c4 = _ccw(p, q, b)
    return (c1 * c2 < 0.0) and (c3 * c4 < 0.0)


@dataclass
class LineCounterState:
    line_id: str
    line_name: str
    in_count: int = 0
    out_count: int = 0
    # Maps track_id -> (last_direction, timestamp)
    track_last_crossed: Dict[int, Tuple[CrossDirection, float]] = field(
        default_factory=dict
    )


class PeopleCounter:
    """
    Manages total room occupancy count, unique visitor IDs, and virtual line IN/OUT counters.
    """

    def __init__(self, debounce_sec: float = 2.0) -> None:
        self.debounce_sec = debounce_sec
        self._line_states: Dict[str, LineCounterState] = {}
        self._unique_seen_ids: Set[int] = set()

    def reset(self) -> None:
        self._line_states.clear()
        self._unique_seen_ids.clear()

    @property
    def total_unique_visitors(self) -> int:
        return len(self._unique_seen_ids)

    def update(
        self,
        tracks: List[TrackedPerson],
        tracker: ByteTracker,
        virtual_lines: List[VirtualLineConfig],
        frame_width: int,
        frame_height: int,
    ) -> List[LineCrossingStats]:
        """
        Update occupancy & evaluate virtual line crossings for all active tracks.
        """
        now_ts = time.monotonic()

        for person in tracks:
            self._unique_seen_ids.add(person.id)

        stats_output: List[LineCrossingStats] = []

        for vline in virtual_lines:
            state = self._line_states.get(vline.id)
            if state is None:
                state = LineCounterState(
                    line_id=vline.id, line_name=vline.name
                )
                self._line_states[vline.id] = state
            else:
                state.line_name = vline.name

            ax = vline.start.x * frame_width
            ay = vline.start.y * frame_height
            bx = vline.end.x * frame_width
            by = vline.end.y * frame_height
            pt_a = (ax, ay)
            pt_b = (bx, by)

            for person in tracks:
                strack = tracker.get_track(person.id)
                if strack is None or len(strack.trajectory) < 2:
                    continue

                p_prev = strack.trajectory[-2]
                p_curr = strack.trajectory[-1]
                pt_p = (float(p_prev[0]), float(p_prev[1]))
                pt_q = (float(p_curr[0]), float(p_curr[1]))

                if not segments_intersect(pt_a, pt_b, pt_p, pt_q):
                    continue

                direction = self._determine_direction(
                    pt_p, pt_q, vline.inDirection
                )
                prev_record = state.track_last_crossed.get(person.id)

                # Anti-double-counting check: ignore duplicate direction or rapid jitter
                if prev_record is not None:
                    last_dir, last_ts = prev_record
                    if last_dir == direction:
                        continue
                    if (now_ts - last_ts) < self.debounce_sec:
                        continue

                state.track_last_crossed[person.id] = (direction, now_ts)
                if direction == "IN":
                    state.in_count += 1
                else:
                    state.out_count += 1

            stats_output.append(
                LineCrossingStats(
                    lineId=state.line_id,
                    lineName=state.line_name,
                    inCount=state.in_count,
                    outCount=state.out_count,
                    netFlow=state.in_count - state.out_count,
                )
            )

        return stats_output

    @staticmethod
    def _determine_direction(
        p_prev: Tuple[float, float],
        p_curr: Tuple[float, float],
        in_dir: Literal["DOWN", "UP", "LEFT", "RIGHT"],
    ) -> CrossDirection:
        dx = p_curr[0] - p_prev[0]
        dy = p_curr[1] - p_prev[1]

        if in_dir == "DOWN":
            return "IN" if dy >= 0 else "OUT"
        if in_dir == "UP":
            return "IN" if dy < 0 else "OUT"
        if in_dir == "RIGHT":
            return "IN" if dx >= 0 else "OUT"
        return "IN" if dx < 0 else "OUT"
