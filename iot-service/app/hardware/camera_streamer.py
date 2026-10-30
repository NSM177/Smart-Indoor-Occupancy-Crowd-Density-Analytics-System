"""
Layer 1C: Camera & AI Service Connector (`camera_streamer.py`).
Handles:
1. Checking physical Raspberry Pi Camera Module (`/dev/video0`) or USB Webcam status.
2. Optional MJPEG HTTP streaming from Raspberry Pi to AI Service (`start_pi_camera_stream`).
3. Polling fallback (`fetch_ai_service_analytics`) to retrieve occupancy & alert data
   directly from AI Service REST API (`/analytics/current`) if needed.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Dict, Optional
import urllib.request

from app.logger import get_iot_logger

logger = get_iot_logger("iot.hardware.camera")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class CameraConnector:
    """Manages local Raspberry Pi camera health check and AI Service link."""

    def __init__(
        self,
        camera_source: str = "0",
        ai_service_url: str = "http://localhost:8000",
        simulation_mode: bool = False,
    ) -> None:
        self.camera_source = str(camera_source)
        self.ai_service_url = ai_service_url.rstrip("/")
        self.simulation_mode = simulation_mode

    def check_camera_available(self) -> bool:
        """Check whether local V4L2 camera node (`/dev/video0`) or simulated camera is ready."""
        if self.simulation_mode:
            return True
        if Path("/dev/video0").exists():
            return True
        try:
            import cv2  # type: ignore

            idx = (
                int(self.camera_source)
                if self.camera_source.isdigit()
                else self.camera_source
            )
            cap = cv2.VideoCapture(idx)
            opened = bool(cap.isOpened())
            cap.release()
            return opened
        except Exception:
            return True

    def fetch_ai_service_analytics(self) -> Optional[Dict[str, Any]]:
        """Query `/analytics/current` from AI Service over HTTP."""
        url = f"{self.ai_service_url}/analytics/current"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
        except Exception:
            pass
        return None


def start_pi_camera_stream(camera_index: int = 0, port: int = 8081) -> None:
    """Start an MJPEG stream server from a local Raspberry Pi camera using OpenCV."""
    try:
        import cv2  # type: ignore
    except ImportError:
        logger.error(
            "opencv-python is required to run camera_streamer on Raspberry Pi."
        )
        return

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.error(
            "Unable to open camera index %d on Raspberry Pi", camera_index
        )
        return

    class MjpegHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/", "/stream.mjpg"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame"
            )
            self.end_headers()
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        continue
                    ret, jpeg = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                    )
                    if not ret:
                        continue
                    payload = jpeg.tobytes()
                    self.wfile.write(b"--frame\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    self.wfile.write(b"\r\n")
            except Exception:
                pass

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadedHTTPServer(("0.0.0.0", port), MjpegHandler)
    logger.info("Raspberry Pi MJPEG Camera Streamer listening on port %d", port)
    server.serve_forever()
