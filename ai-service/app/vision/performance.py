"""
Module 7: Performance Optimizer & Profiler (`performance.py`).
Provides frame-skipping control for Raspberry Pi 4/5 and measures rolling averages of
FPS, YOLO inference latency (ms), and end-to-end frame processing latency (ms).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Tuple

from app.schemas.vision_schema import PerformanceMetrics


class PerformanceProfiler:
    """Tracks FPS, inference time (ms), processing time (ms), and frame skipping."""

    def __init__(
        self,
        frame_skip: int = 1,
        inference_resolution: Tuple[int, int] = (640, 384),
        window_size: int = 30,
    ) -> None:
        self.frame_skip = max(1, frame_skip)
        self.inference_resolution = inference_resolution
        self._inference_times_ms: Deque[float] = deque(maxlen=window_size)
        self._processing_times_ms: Deque[float] = deque(maxlen=window_size)
        self._frame_timestamps: Deque[float] = deque(maxlen=window_size)
        self.total_frames_processed: int = 0

    def should_run_detection(self) -> bool:
        """
        Return True if full YOLO detection should execute on the current frame.
        When `frame_skip == 1`, runs on every frame.
        When `frame_skip == N`, runs on every N-th frame and uses ByteTrack motion prediction
        on intermediate frames.
        """
        return (self.total_frames_processed % self.frame_skip) == 0

    def record_frame(
        self, inference_ms: float, processing_ms: float
    ) -> PerformanceMetrics:
        now = time.perf_counter()
        self.total_frames_processed += 1
        if inference_ms > 0:
            self._inference_times_ms.append(inference_ms)
        self._processing_times_ms.append(processing_ms)
        self._frame_timestamps.append(now)

        return self.get_metrics()

    def get_metrics(
        self, model_backend: str = "pytorch-ultralytics"
    ) -> PerformanceMetrics:
        avg_inf = (
            sum(self._inference_times_ms) / len(self._inference_times_ms)
            if self._inference_times_ms
            else 0.0
        )
        avg_proc = (
            sum(self._processing_times_ms) / len(self._processing_times_ms)
            if self._processing_times_ms
            else 0.0
        )

        fps = 0.0
        if len(self._frame_timestamps) >= 2:
            span = self._frame_timestamps[-1] - self._frame_timestamps[0]
            if span > 1e-6:
                fps = (len(self._frame_timestamps) - 1) / span
        elif avg_proc > 0:
            fps = min(60.0, 1000.0 / avg_proc)

        return PerformanceMetrics(
            fps=round(fps, 1),
            inferenceTimeMs=round(avg_inf, 2),
            processingTimeMs=round(avg_proc, 2),
            frameSkip=self.frame_skip,
            inferenceResolution=self.inference_resolution,
            modelBackend=model_backend,
            totalFramesProcessed=self.total_frames_processed,
        )
