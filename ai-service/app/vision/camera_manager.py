"""
Multi-threaded Camera & Video Stream Reader (`camera_manager.py`).
Supports:
- USB Webcam index (`"0"`, `"1"`)
- Raspberry Pi Camera Module (`"picamera"` or V4L2 `/dev/video0` or RTSP/HTTP stream)
- RTSP / HTTP / MJPEG IP camera streams
- Local video files (`.mp4`, `.avi`, `.mkv`) for offline testing before deploying to Raspberry Pi
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

            if (
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
            sleep_sec = max(0.001, frame_interval - elapsed_step)
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
