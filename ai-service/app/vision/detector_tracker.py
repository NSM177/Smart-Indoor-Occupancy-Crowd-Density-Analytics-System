"""
Person Detection & Multi-Object Tracking using Ultralytics YOLO + ByteTrack.
Tracks each person with a persistent `track_id` to prevent double counting
and computes per-person dwell time (seconds present in the scene).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from app.core.logger import get_logger
from app.schemas.vision_schema import NormalizedPoint, TrackedPerson

logger = get_logger("ai.detector_tracker")


@dataclass
class TrackHistoryEntry:
    track_id: int
    first_seen_ts: float
    last_seen_ts: float
    current_zone_id: Optional[str] = None
    zone_entered_ts: float = 0.0


class PersonDetectorTracker:
    """Runs YOLO person detection (COCO class 0) and ByteTrack tracking on video frames."""

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        track_buffer_sec: float = 5.0,
    ) -> None:
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.track_buffer_sec = track_buffer_sec

        self._model = None
        self._model_loaded = False
        self._track_history: Dict[int, TrackHistoryEntry] = {}
        self._load_model()

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO  # type: ignore

            logger.info("Loading YOLO model from '%s'...", self.model_path)
            self._model = YOLO(self.model_path)
            self._model_loaded = True
            logger.info("YOLO + ByteTrack model initialized successfully.")
        except Exception as exc:
            self._model_loaded = False
            logger.error(
                "Failed to load Ultralytics YOLO model (%s): %s",
                self.model_path,
                exc,
            )

    @property
    def is_ready(self) -> bool:
        return self._model_loaded and self._model is not None

    def detect_and_track(self, frame: np.ndarray) -> List[TrackedPerson]:
        """
        Execute YOLO person detection + ByteTrack on a BGR frame.
        Returns a list of `TrackedPerson` with normalized foot points and dwell time.
        """
        if frame is None or frame.size == 0:
            return []

        height, width = frame.shape[:2]
        now_ts = time.monotonic()
        tracked_persons: List[TrackedPerson] = []

        if not self.is_ready:
            return []

        try:
            results = self._model.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[0],  # COCO class 0 = person
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )

            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy_arr = boxes.xyxy.cpu().numpy()
                    confs = (
                        boxes.conf.cpu().numpy()
                        if boxes.conf is not None
                        else np.ones(len(xyxy_arr))
                    )
                    track_ids = (
                        boxes.id.int().cpu().numpy()
                        if boxes.id is not None
                        else np.arange(1, len(xyxy_arr) + 1)
                    )

                    for idx, box in enumerate(xyxy_arr):
                        x1, y1, x2, y2 = (
                            max(0, int(box[0])),
                            max(0, int(box[1])),
                            min(width - 1, int(box[2])),
                            min(height - 1, int(box[3])),
                        )
                        track_id = int(track_ids[idx])
                        conf = float(confs[idx])

                        # Foot point = bottom-center of bounding box
                        foot_x_px = int((x1 + x2) * 0.5)
                        foot_y_px = int(y2)
                        norm_x = round(
                            min(1.0, max(0.0, foot_x_px / float(width))), 4
                        )
                        norm_y = round(
                            min(1.0, max(0.0, foot_y_px / float(height))), 4
                        )

                        entry = self._track_history.get(track_id)
                        if entry is None:
                            entry = TrackHistoryEntry(
                                track_id=track_id,
                                first_seen_ts=now_ts,
                                last_seen_ts=now_ts,
                                zone_entered_ts=now_ts,
                            )
                            self._track_history[track_id] = entry
                        else:
                            entry.last_seen_ts = now_ts

                        dwell_sec = round(now_ts - entry.first_seen_ts, 1)

                        tracked_persons.append(
                            TrackedPerson(
                                id=track_id,
                                bbox=(x1, y1, x2, y2),
                                confidence=round(conf, 3),
                                footPoint=NormalizedPoint(x=norm_x, y=norm_y),
                                footPointPx=(foot_x_px, foot_y_px),
                                dwellSec=dwell_sec,
                            )
                        )
        except Exception as exc:
            logger.warning("YOLO+ByteTrack inference error: %s", exc)

        # Prune expired tracks from history
        stale_ids = [
            tid
            for tid, hist in self._track_history.items()
            if now_ts - hist.last_seen_ts > self.track_buffer_sec
        ]
        for tid in stale_ids:
            self._track_history.pop(tid, None)

        return tracked_persons
