"""
Multi-threaded Camera & Video Stream Reader (`camera_manager.py`).
Supports:
- USB Webcam index (`"0"`, `"1"`)
- Raspberry Pi Camera Module (`"picamera"` or V4L2 `/dev/video0` or RTSP/HTTP stream)
- RTSP / HTTP / MJPEG IP camera streams
- Local video files (`.mp4`, `.avi`, `.mkv`) for offline testing before deploying to Raspberry Pi
- Frames pushed from a browser webcam (`"browser"`), since a Docker container cannot open the host camera
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np

from app.core.logger import get_logger

logger = get_logger("ai.camera_manager")

# `stream_url` value for frames pushed through `push_frame` instead of being read
BROWSER_SOURCE = "browser"
# Pushed frames older than this mean the browser stopped sending (tab closed, camera off)
BROWSER_FRAME_STALE_SEC = 3.0


def letterbox_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Fit a frame into width x height keeping its aspect ratio (black bars)."""
    src_h, src_w = frame.shape[:2]
    if src_w == width and src_h == height:
        return frame
    scale = min(width / src_w, height / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    top = (height - new_h) // 2
    left = (width - new_w) // 2
    canvas[top : top + new_h, left : left + new_w] = resized
    return canvas


class CameraStreamReader:
    """Continuously captures frames from a camera or video source in a background thread."""

    def __init__(
        self,
        camera_id: str,
        stream_url: str = "0",
        target_width: int = 1280,
        target_height: int = 720,
        target_fps: int = 15,
    ) -> None:
        self.camera_id = camera_id
        self.stream_url = str(stream_url).strip()
        self.target_width = target_width
        self.target_height = target_height
        self.target_fps = max(1, target_fps)

        self._lock = threading.RLock()
        self._frame: Optional[np.ndarray] = None
        self._is_hardware_connected: bool = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._capture: Optional[cv2.VideoCapture] = None
        self._actual_fps: float = 0.0

        # Runtime source switching (applied on the capture thread)
        self._pending_switch: Optional[Tuple[str, bool]] = None
        # Uploaded videos play at their own speed and keep their aspect ratio
        self._realtime_source: bool = False
        self._file_frame_interval: Optional[float] = None
        self._pushed_frame: Optional[np.ndarray] = None
        self._pushed_frame_ts: float = 0.0
        self._pushed_count: int = 0
        self._pushed_window_start: float = time.monotonic()

    def _parse_source(self) -> Union[int, str]:
        cleaned = self.stream_url.strip()
        if cleaned.lower() == "picamera":
            return 0
        if cleaned.isdigit():
            return int(cleaned)
        return cleaned

    def _is_video_file(self) -> bool:
        src = self._parse_source()
        if isinstance(src, int):
            return False
        if src.startswith(("rtsp://", "rtsps://", "http://", "https://")):
            return False
        return Path(src).exists()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"CameraReader-{self.camera_id}",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._release_capture()

    def update_source(
        self,
        stream_url: str,
        target_width: int = 1280,
        target_height: int = 720,
        target_fps: int = 15,
    ) -> None:
        changed = (
            str(stream_url).strip() != self.stream_url
            or target_width != self.target_width
            or target_height != self.target_height
        )
        self.stream_url = str(stream_url).strip()
        self.target_width = target_width
        self.target_height = target_height
        self.target_fps = max(1, target_fps)
        if changed:
            logger.info(
                "Updating camera %s source to '%s' (%dx%d @ %d FPS)",
                self.camera_id,
                self.stream_url,
                self.target_width,
                self.target_height,
                self.target_fps,
            )
            self._release_capture()

    def switch_source(self, stream_url: str, realtime_source: bool = False) -> None:
        """
        Change the source at runtime. The capture thread applies it, so the OpenCV
        capture is never released while that thread is reading from it.
        """
        with self._lock:
            self._pending_switch = (str(stream_url).strip(), realtime_source)
        if self._thread is None or not self._thread.is_alive():
            self._apply_pending_switch()

    def _apply_pending_switch(self) -> bool:
        with self._lock:
            pending = self._pending_switch
            self._pending_switch = None
        if pending is None:
            return False
        self._release_capture()
        self.stream_url, self._realtime_source = pending
        self._file_frame_interval = None
        with self._lock:
            self._pushed_frame = None
            self._pushed_frame_ts = 0.0
        logger.info(
            "Switched camera %s source to '%s'", self.camera_id, self.stream_url
        )
        return True

    def push_frame(self, frame: np.ndarray) -> None:
        """Accept one BGR frame from an external producer (browser webcam)."""
        fitted = letterbox_frame(frame, self.target_width, self.target_height)
        now = time.monotonic()
        with self._lock:
            self._pushed_frame = fitted
            self._pushed_frame_ts = now
            self._pushed_count += 1
            elapsed = now - self._pushed_window_start
            if elapsed >= 1.0:
                self._actual_fps = round(self._pushed_count / elapsed, 1)
                self._pushed_count = 0
                self._pushed_window_start = now

    def _publish_pushed_frame(self) -> None:
        now = time.monotonic()
        with self._lock:
            pushed = self._pushed_frame
            fresh = (
                pushed is not None
                and (now - self._pushed_frame_ts) <= BROWSER_FRAME_STALE_SEC
            )
        frame = pushed if fresh else self._build_standby_frame()
        with self._lock:
            self._frame = frame
            self._is_hardware_connected = fresh

    def _release_capture(self) -> None:
        with self._lock:
            if self._capture is not None:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
            self._is_hardware_connected = False

    def _open_capture(self) -> bool:
        source = self._parse_source()
        try:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                return False

            if not self._is_video_file():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            elif self._realtime_source:
                source_fps = cap.get(cv2.CAP_PROP_FPS)
                self._file_frame_interval = (
                    1.0 / source_fps if 1.0 <= source_fps <= 120.0 else None
                )

            with self._lock:
                self._capture = cap
                self._is_hardware_connected = True
            logger.info(
                "Opened video/camera source '%s' for camera %s",
                self.stream_url,
                self.camera_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Error opening camera source '%s': %s", self.stream_url, exc
            )
            return False

    def _capture_loop(self) -> None:
        last_retry_ts = 0.0
        frame_interval = 1.0 / float(self.target_fps)
        fps_counter = 0
        fps_window_start = time.monotonic()

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            if self._apply_pending_switch():
                last_retry_ts = 0.0

            if self.stream_url == BROWSER_SOURCE:
                self._publish_pushed_frame()
                self._stop_event.wait(frame_interval)
                continue

            if self._capture is None or not self._is_hardware_connected:
                if loop_start - last_retry_ts >= 5.0:
                    last_retry_ts = loop_start
                    self._open_capture()

                if not self._is_hardware_connected:
                    diag_frame = self._build_standby_frame()
                    with self._lock:
                        self._frame = diag_frame
                        self._actual_fps = float(self.target_fps)
                    self._stop_event.wait(frame_interval)
                    continue

            ok = False
            raw_frame: Optional[np.ndarray] = None
            try:
                if self._capture is not None:
                    ok, raw_frame = self._capture.read()
                    # Loop video file back to frame 0 when reaching EOF
                    if not ok and self._is_video_file():
                        self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, raw_frame = self._capture.read()
            except Exception as exc:
                logger.warning("Exception reading camera frame: %s", exc)
                ok = False

            if not ok or raw_frame is None:
                logger.warning(
                    "Camera stream '%s' lost frame; reconnecting...",
                    self.stream_url,
                )
                self._release_capture()
                self._stop_event.wait(0.5)
                continue

            if self._realtime_source:
                raw_frame = letterbox_frame(
                    raw_frame, self.target_width, self.target_height
                )
            elif (
                raw_frame.shape[1] != self.target_width
                or raw_frame.shape[0] != self.target_height
            ):
                raw_frame = cv2.resize(
                    raw_frame,
                    (self.target_width, self.target_height),
                    interpolation=cv2.INTER_LINEAR,
                )

            fps_counter += 1
            elapsed_window = time.monotonic() - fps_window_start
            if elapsed_window >= 1.0:
                self._actual_fps = round(fps_counter / elapsed_window, 1)
                fps_counter = 0
                fps_window_start = time.monotonic()

            with self._lock:
                self._frame = raw_frame

            elapsed_step = time.monotonic() - loop_start
            sleep_sec = max(
                0.001, (self._file_frame_interval or frame_interval) - elapsed_step
            )
            self._stop_event.wait(sleep_sec)

    def _build_standby_frame(self) -> np.ndarray:
        """Render an OpenCV standby frame when no physical camera is plugged in."""
        canvas = np.full(
            (self.target_height, self.target_width, 3),
            (28, 32, 42),
            dtype=np.uint8,
        )
        step = 64
        for x in range(0, self.target_width, step):
            cv2.line(canvas, (x, 0), (x, self.target_height), (42, 48, 62), 1)
        for y in range(0, self.target_height, step):
            cv2.line(canvas, (0, y), (self.target_width, y), (42, 48, 62), 1)

        cv2.putText(
            canvas,
            f"CAMERA SOURCE ({self.stream_url}) STANDBY - AWAITING VIDEO INPUT",
            (40, self.target_height - 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (160, 175, 200),
            2,
            cv2.LINE_AA,
        )
        return canvas

    def get_latest_frame(self) -> Tuple[Optional[np.ndarray], float, bool]:
        """Return (frame_copy, actual_fps, is_hardware_connected)."""
        with self._lock:
            if self._frame is None:
                return None, 0.0, False
            return (
                self._frame.copy(),
                self._actual_fps,
                self._is_hardware_connected,
            )
