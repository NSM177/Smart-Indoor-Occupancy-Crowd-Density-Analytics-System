"""
Module 2: Multi-Object Tracking Engine (`tracker.py`) - ByteTrack Implementation.

Algorithm Explanation (ByteTrack - Zhang et al., ECCV 2022):
1. Detections from the current frame are split into two sets based on confidence:
   - D_high: detections with confidence >= `high_thresh` (e.g. 0.35)
   - D_low:  detections with `low_thresh` <= confidence < `high_thresh` (e.g. 0.15 .. 0.35)
2. Motion Prediction:
   - Every active (`TRACKED`) and recently lost (`LOST`) track predicts its new bounding box
     in the current frame using an exponentially smoothed constant-velocity motion model.
3. First Association (High-Confidence Matching):
   - Active and lost tracks are matched against `D_high` using IoU distance matrix matching.
   - Matched tracks update their velocity, bounding box, foot point, and trajectory.
4. Second Association (Low-Confidence / Occlusion Recovery):
   - Remaining unmatched `TRACKED` tracks are matched against `D_low` using IoU.
   - When a person is partially occluded by another person or furniture, their YOLO confidence
     drops into `D_low`. Stage 2 preserves their `track_id` and prevents ID switching or
     double counting when they emerge from occlusion.
5. Track Lifecycle & Coasting:
   - Unmatched tracks transition to `LOST` and are retained for up to `max_time_lost`
     (`track_buffer`) frames before removal, allowing recovery across full short-term occlusions.
   - Unmatched `D_high` detections initialize new tracks with unique monotonic `track_id`s.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Literal, Optional, Tuple

import numpy as np

from app.schemas.vision_schema import (
    NormalizedPoint,
    RawDetection,
    TrackedPerson,
)

TrackState = Literal["TRACKED", "LOST", "REMOVED"]


def compute_iou_matrix(
    boxes_a: np.ndarray, boxes_b: np.ndarray
) -> np.ndarray:
    """
    Compute pairwise Intersection-over-Union (IoU) matrix between two sets of boxes.
    `boxes_a`: shape (N, 4) in [x1, y1, x2, y2]
    `boxes_b`: shape (M, 4) in [x1, y1, x2, y2]
    Returns:
        iou_matrix of shape (N, M) with values in [0.0, 1.0].
    """
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)

    a = boxes_a.astype(np.float32)
    b = boxes_b.astype(np.float32)

    inter_x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    inter_y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    inter_x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    inter_y2 = np.minimum(a[:, None, 3], b[None, :, 3])

    inter_w = np.maximum(0.0, inter_x2 - inter_x1)
    inter_h = np.maximum(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = np.maximum(1.0, (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1]))
    area_b = np.maximum(1.0, (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]))

    union_area = area_a[:, None] + area_b[None, :] - inter_area
    return np.where(union_area > 0, inter_area / union_area, 0.0)


def match_by_iou(
    tracks_boxes: np.ndarray,
    det_boxes: np.ndarray,
    iou_threshold: float,
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """
    Perform bipartite matching on the IoU matrix above `iou_threshold`.
    Returns:
        (matched_pairs, unmatched_track_indices, unmatched_det_indices)
    """
    num_tracks = len(tracks_boxes)
    num_dets = len(det_boxes)

    if num_tracks == 0 or num_dets == 0:
        return [], list(range(num_tracks)), list(range(num_dets))

    iou_mat = compute_iou_matrix(tracks_boxes, det_boxes)
    matched_pairs: List[Tuple[int, int]] = []
    used_tracks = set()
    used_dets = set()

    # Sort all candidate pairs by descending IoU for optimal greedy assignment
    flat_indices = np.argsort(-iou_mat, axis=None)
    for flat_idx in flat_indices:
        t_idx = int(flat_idx // num_dets)
        d_idx = int(flat_idx % num_dets)
        score = float(iou_mat[t_idx, d_idx])
        if score < iou_threshold:
            break
        if t_idx in used_tracks or d_idx in used_dets:
            continue
        used_tracks.add(t_idx)
        used_dets.add(d_idx)
        matched_pairs.append((t_idx, d_idx))

    unmatched_tracks = [i for i in range(num_tracks) if i not in used_tracks]
    unmatched_dets = [j for j in range(num_dets) if j not in used_dets]
    return matched_pairs, unmatched_tracks, unmatched_dets


@dataclass
class STrack:
    """Single Track object representing an individual person across frames."""

    track_id: int
    bbox: np.ndarray  # [x1, y1, x2, y2] float32
    confidence: float
    first_seen_ts: float
    last_seen_ts: float
    frame_id: int
    state: TrackState = "TRACKED"
    lost_frames: int = 0
    hits: int = 1
    velocity: np.ndarray = field(
        default_factory=lambda: np.zeros(4, dtype=np.float32)
    )
    trajectory: Deque[Tuple[int, int]] = field(
        default_factory=lambda: deque(maxlen=40)
    )

    def __post_init__(self) -> None:
        fx, fy = self.foot_point_px
        self.trajectory.append((fx, fy))

    @property
    def foot_point_px(self) -> Tuple[int, int]:
        x1, _y1, x2, y2 = self.bbox
        return int(round((x1 + x2) * 0.5)), int(round(y2))

    def predict(self) -> None:
        """Advance bounding box using constant-velocity motion model."""
        decay = 0.85 if self.state == "LOST" else 1.0
        self.bbox = self.bbox + self.velocity * decay
        self.velocity *= decay

    def update(
        self,
        new_bbox: Tuple[int, int, int, int],
        new_conf: float,
        frame_id: int,
        now_ts: float,
    ) -> None:
        new_arr = np.array(new_bbox, dtype=np.float32)
        dt_frames = max(1, frame_id - self.frame_id)
        instant_vel = (new_arr - self.bbox) / float(dt_frames)
        # Exponentially smoothed velocity
        self.velocity = 0.6 * self.velocity + 0.4 * instant_vel
        self.bbox = new_arr
        self.confidence = new_conf
        self.frame_id = frame_id
        self.last_seen_ts = now_ts
        self.state = "TRACKED"
        self.lost_frames = 0
        self.hits += 1
        self.trajectory.append(self.foot_point_px)


class ByteTracker:
    """
    Two-stage ByteTrack Multi-Object Tracker for person tracking & occlusion handling.
    """

    def __init__(
        self,
        high_thresh: float = 0.35,
        low_thresh: float = 0.15,
        match_iou_thresh: float = 0.25,
        second_match_iou_thresh: float = 0.20,
        track_buffer: int = 30,
    ) -> None:
        self.high_thresh = high_thresh
        self.low_thresh = low_thresh
        self.match_iou_thresh = match_iou_thresh
        self.second_match_iou_thresh = second_match_iou_thresh
        self.track_buffer = max(1, track_buffer)

        self.frame_id: int = 0
        self._next_track_id: int = 1
        self._tracks: Dict[int, STrack] = {}

    def reset(self) -> None:
        self.frame_id = 0
        self._next_track_id = 1
        self._tracks.clear()

    def get_track(self, track_id: int) -> Optional[STrack]:
        return self._tracks.get(track_id)

    def predict_only(
        self, frame_width: int, frame_height: int
    ) -> List[TrackedPerson]:
        """
        Used during Frame Skipping: predicts positions of active tracks without running YOLO.
        """
        self.frame_id += 1
        now_ts = time.monotonic()
        active_outputs: List[TrackedPerson] = []

        for track in list(self._tracks.values()):
            if track.state == "TRACKED":
                track.predict()
                active_outputs.append(
                    self._to_tracked_person(
                        track, frame_width, frame_height, now_ts
                    )
                )
        return active_outputs

    def update(
        self,
        detections: List[RawDetection],
        frame_width: int,
        frame_height: int,
    ) -> List[TrackedPerson]:
        """
        Execute ByteTrack two-stage association on current frame detections.
        """
        self.frame_id += 1
        now_ts = time.monotonic()

        # 1. Split detections into D_high and D_low
        dets_high = [d for d in detections if d.confidence >= self.high_thresh]
        dets_low = [
            d
            for d in detections
            if self.low_thresh <= d.confidence < self.high_thresh
        ]

        # 2. Predict next state for all active (TRACKED) and LOST tracks
        pool_tracks = [
            t
            for t in self._tracks.values()
            if t.state in ("TRACKED", "LOST")
        ]
        for track in pool_tracks:
            track.predict()

        # 3. Stage 1: Match pool_tracks with D_high
        pool_boxes = (
            np.array([t.bbox for t in pool_tracks], dtype=np.float32)
            if pool_tracks
            else np.zeros((0, 4), dtype=np.float32)
        )
        high_boxes = (
            np.array([d.bbox for d in dets_high], dtype=np.float32)
            if dets_high
            else np.zeros((0, 4), dtype=np.float32)
        )

        matched_1, unmatched_track_idxs_1, unmatched_high_idxs = match_by_iou(
            pool_boxes, high_boxes, self.match_iou_thresh
        )

        for t_idx, d_idx in matched_1:
            track = pool_tracks[t_idx]
            det = dets_high[d_idx]
            track.update(det.bbox, det.confidence, self.frame_id, now_ts)

        # 4. Stage 2: Match remaining TRACKED tracks with D_low (Occlusion recovery)
        remaining_tracked = [
            pool_tracks[i]
            for i in unmatched_track_idxs_1
            if pool_tracks[i].state == "TRACKED"
        ]
        remaining_lost = [
            pool_tracks[i]
            for i in unmatched_track_idxs_1
            if pool_tracks[i].state == "LOST"
        ]

        rem_boxes = (
            np.array([t.bbox for t in remaining_tracked], dtype=np.float32)
            if remaining_tracked
            else np.zeros((0, 4), dtype=np.float32)
        )
        low_boxes = (
            np.array([d.bbox for d in dets_low], dtype=np.float32)
            if dets_low
            else np.zeros((0, 4), dtype=np.float32)
        )

        matched_2, unmatched_track_idxs_2, _unmatched_low_idxs = match_by_iou(
            rem_boxes, low_boxes, self.second_match_iou_thresh
        )

        for t_idx, d_idx in matched_2:
            track = remaining_tracked[t_idx]
            det = dets_low[d_idx]
            track.update(det.bbox, det.confidence, self.frame_id, now_ts)

        # 5. Mark still-unmatched tracks as LOST and increment lost_frames
        for t_idx in unmatched_track_idxs_2:
            track = remaining_tracked[t_idx]
            track.state = "LOST"
            track.lost_frames += 1

        for track in remaining_lost:
            track.lost_frames += 1

        # 6. Initialize new tracks for unmatched high-confidence detections
        for d_idx in unmatched_high_idxs:
            det = dets_high[d_idx]
            new_id = self._next_track_id
            self._next_track_id += 1
            self._tracks[new_id] = STrack(
                track_id=new_id,
                bbox=np.array(det.bbox, dtype=np.float32),
                confidence=det.confidence,
                first_seen_ts=now_ts,
                last_seen_ts=now_ts,
                frame_id=self.frame_id,
                state="TRACKED",
            )

        # 7. Prune tracks that exceeded `track_buffer` lost frames
        expired_ids = [
            tid
            for tid, trk in self._tracks.items()
            if trk.state == "LOST" and trk.lost_frames > self.track_buffer
        ]
        for tid in expired_ids:
            self._tracks.pop(tid, None)

        # 8. Build output list of active TrackedPerson objects
        outputs: List[TrackedPerson] = []
        for track in self._tracks.values():
            if track.state == "TRACKED":
                outputs.append(
                    self._to_tracked_person(
                        track, frame_width, frame_height, now_ts
                    )
                )

        return outputs

    @staticmethod
    def _to_tracked_person(
        track: STrack,
        frame_width: int,
        frame_height: int,
        now_ts: float,
    ) -> TrackedPerson:
        x1 = max(0, min(frame_width - 1, int(round(track.bbox[0]))))
        y1 = max(0, min(frame_height - 1, int(round(track.bbox[1]))))
        x2 = max(0, min(frame_width - 1, int(round(track.bbox[2]))))
        y2 = max(0, min(frame_height - 1, int(round(track.bbox[3]))))

        fx, fy = int((x1 + x2) * 0.5), int(y2)
        norm_x = round(min(1.0, max(0.0, fx / float(max(1, frame_width)))), 4)
        norm_y = round(min(1.0, max(0.0, fy / float(max(1, frame_height)))), 4)
        dwell_sec = round(max(0.0, now_ts - track.first_seen_ts), 1)

        return TrackedPerson(
            id=track.track_id,
            bbox=(x1, y1, x2, y2),
            confidence=round(float(track.confidence), 3),
            footPoint=NormalizedPoint(x=norm_x, y=norm_y),
            footPointPx=(fx, fy),
            dwellSec=dwell_sec,
            isOccluded=track.lost_frames > 0,
        )
