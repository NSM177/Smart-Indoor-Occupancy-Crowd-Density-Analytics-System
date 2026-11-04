"""
Selectable video input for the AI pipeline (`video_source.py`):
- `default`: the configured `CAMERA_SOURCE` / room camera (startup behaviour)
- `video`:   a video file uploaded by an operator, looped like a camera feed
- `browser`: frames pushed from the webcam of the operator's browser
"""

from __future__ import annotations

from pathlib import Path
import re
import threading
from typing import Any, Callable, Dict, Optional
import uuid

import cv2
import numpy as np

from app.core.logger import get_logger
from app.vision.camera_manager import BROWSER_SOURCE, CameraStreamReader

logger = get_logger("ai.video_source")

SOURCE_DEFAULT = "default"
SOURCE_VIDEO = "video"
SOURCE_BROWSER = "browser"

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


class VideoSourceError(Exception):
    """A source operation was rejected; `status_code` is the HTTP status to report."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class VideoSourceManager:
    """Tracks the active source mode and the single uploaded demo video."""

    def __init__(
        self,
        reader: CameraStreamReader,
        upload_dir: str,
        on_source_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self._reader = reader
        self._upload_dir = Path(upload_dir)
        self._on_source_changed = on_source_changed
        self._lock = threading.RLock()
        self._mode = SOURCE_DEFAULT
        self._default_source = reader.stream_url
        self._uploaded_path: Optional[Path] = None
        self._uploaded_name: Optional[str] = None

    @property
    def mode(self) -> str:
        return self._mode

    def set_default_source(self, stream_url: str) -> None:
        """Remember the configured camera so `default` returns to the latest one."""
        with self._lock:
            self._default_source = str(stream_url).strip()

    def select(self, mode: str) -> Dict[str, Any]:
        with self._lock:
            if mode == SOURCE_DEFAULT:
                self._reader.switch_source(self._default_source)
            elif mode == SOURCE_BROWSER:
                self._reader.switch_source(BROWSER_SOURCE, realtime_source=True)
            elif mode == SOURCE_VIDEO:
                if self._uploaded_path is None or not self._uploaded_path.exists():
                    raise VideoSourceError(
                        "No uploaded video is available. Upload one first.", 409
                    )
                self._reader.switch_source(
                    str(self._uploaded_path), realtime_source=True
                )
            else:
                raise VideoSourceError(f"Unknown video source '{mode}'.", 400)
            self._mode = mode
        logger.info("Video source mode set to '%s'", mode)
        if self._on_source_changed is not None:
            self._on_source_changed()
        return self.status()

    def new_upload_path(self, filename: str) -> Path:
        """Validate the client file name and return a server-generated temp path."""
        extension = Path(filename or "").suffix.lower()
        if extension not in ALLOWED_VIDEO_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_VIDEO_EXTENSIONS))
            raise VideoSourceError(
                f"Unsupported video type '{extension}'. Allowed: {allowed}.", 415
            )
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        return self._upload_dir / f"upload_{uuid.uuid4().hex}{extension}"

    def activate_upload(self, path: Path, original_name: str) -> Dict[str, Any]:
        """Check the stored file really is a readable video, then start playing it."""
        capture = cv2.VideoCapture(str(path))
        try:
            readable = capture.isOpened() and capture.read()[0]
        finally:
            capture.release()
        if not readable:
            path.unlink(missing_ok=True)
            raise VideoSourceError(
                "The uploaded file could not be decoded as a video.", 422
            )

        with self._lock:
            previous = self._uploaded_path
            self._uploaded_path = path
            self._uploaded_name = re.split(r"[\\/]", original_name)[-1]
            status = self.select(SOURCE_VIDEO)
        if previous is not None and previous != path:
            try:
                previous.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not delete old upload %s: %s", previous, exc)
        return status

    def push_browser_frame(self, jpeg_bytes: bytes) -> None:
        if self._mode != SOURCE_BROWSER:
            raise VideoSourceError("The active video source is not the browser.", 409)
        frame = cv2.imdecode(
            np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if frame is None:
            raise VideoSourceError("The frame is not a valid image.", 422)
        self._reader.push_frame(frame)

    def status(self) -> Dict[str, Any]:
        _, fps, connected = self._reader.get_latest_frame()
        with self._lock:
            return {
                "mode": self._mode,
                "connected": connected,
                "fps": fps,
                "uploaded_video": self._uploaded_name,
                "default_source": self._default_source,
            }
