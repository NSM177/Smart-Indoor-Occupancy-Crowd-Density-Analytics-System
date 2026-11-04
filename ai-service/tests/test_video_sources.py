"""
Tests for the selectable demo video inputs:
1. CameraStreamReader runtime switching, pushed frames and aspect-preserving resize
2. VideoSourceManager modes and upload validation
3. /sources REST routes (auth, upload limits, frame push)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import cv2
from fastapi import FastAPI
from fastapi.testclient import TestClient
import jwt
import numpy as np

from app.api.source_routes import router as source_router
from app.core.config import settings
from app.services.video_source import (
    SOURCE_BROWSER,
    SOURCE_DEFAULT,
    SOURCE_VIDEO,
    VideoSourceError,
    VideoSourceManager,
)
from app.vision import camera_manager
from app.vision.camera_manager import (
    BROWSER_SOURCE,
    CameraStreamReader,
    letterbox_frame,
)


def write_test_video(path: Path, frames: int = 12) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (320, 240)
    )
    for index in range(frames):
        frame = np.full((240, 320, 3), index * 10 % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def jpeg_bytes(width: int = 64, height: int = 48) -> bytes:
    frame = np.full((height, width, 3), 200, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def make_token(role: str = "OPERATOR", token_type: str = "access", **overrides) -> str:
    payload = {
        "sub": "user-1",
        "role": role,
        "type": token_type,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        **overrides,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class TestCameraReaderSources(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = CameraStreamReader(
            "test", stream_url="no-such-source", target_width=320, target_height=180
        )

    def tearDown(self) -> None:
        self.reader.stop()

    def test_letterbox_keeps_aspect_ratio(self) -> None:
        portrait = np.full((400, 200, 3), 255, dtype=np.uint8)
        fitted = letterbox_frame(portrait, 320, 180)
        self.assertEqual(fitted.shape, (180, 320, 3))
        self.assertEqual(int(fitted[90, 10].sum()), 0)  # side bar stays black
        self.assertEqual(int(fitted[90, 160].sum()), 255 * 3)  # picture is centered

    def test_pushed_frames_connect_then_go_stale(self) -> None:
        self.reader.start()
        self.reader.switch_source(BROWSER_SOURCE, realtime_source=True)
        self.assertTrue(wait_until(lambda: self.reader.stream_url == BROWSER_SOURCE))
        self.assertFalse(self.reader.get_latest_frame()[2])

        self.reader.push_frame(np.full((48, 64, 3), 200, dtype=np.uint8))
        self.assertTrue(wait_until(lambda: self.reader.get_latest_frame()[2]))
        frame = self.reader.get_latest_frame()[0]
        self.assertEqual(frame.shape, (180, 320, 3))

        with mock.patch.object(camera_manager, "BROWSER_FRAME_STALE_SEC", 0.05):
            self.assertTrue(wait_until(lambda: not self.reader.get_latest_frame()[2]))

    def test_switch_to_video_file_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.avi"
            write_test_video(video)
            self.reader.start()
            self.reader.switch_source(str(video), realtime_source=True)
            self.assertTrue(wait_until(lambda: self.reader.get_latest_frame()[2]))
            self.reader.stop()


class TestVideoSourceManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.reader = CameraStreamReader(
            "test", stream_url="0", target_width=320, target_height=180
        )
        self.changes = []
        self.manager = VideoSourceManager(
            self.reader, self.tmp.name, lambda: self.changes.append(True)
        )

    def tearDown(self) -> None:
        self.reader.stop()
        self.tmp.cleanup()

    def test_starts_on_the_configured_camera(self) -> None:
        status = self.manager.status()
        self.assertEqual(status["mode"], SOURCE_DEFAULT)
        self.assertEqual(status["default_source"], "0")
        self.assertIsNone(status["uploaded_video"])

    def test_select_video_requires_an_upload(self) -> None:
        with self.assertRaises(VideoSourceError) as ctx:
            self.manager.select(SOURCE_VIDEO)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(self.manager.mode, SOURCE_DEFAULT)

    def test_upload_replaces_previous_and_default_restores_camera(self) -> None:
        first = self.manager.new_upload_path("a.avi")
        write_test_video(first)
        self.manager.activate_upload(first, "C:\\clips\\lobby.avi")
        self.assertEqual(self.manager.mode, SOURCE_VIDEO)
        self.assertEqual(self.manager.status()["uploaded_video"], "lobby.avi")
        self.assertEqual(self.reader.stream_url, str(first))

        second = self.manager.new_upload_path("b.avi")
        write_test_video(second)
        self.manager.activate_upload(second, "hall.avi")
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())

        self.manager.select(SOURCE_DEFAULT)
        self.assertEqual(self.reader.stream_url, "0")
        self.assertEqual(len(self.changes), 3)

    def test_rejects_bad_type_and_undecodable_file(self) -> None:
        with self.assertRaises(VideoSourceError) as ctx:
            self.manager.new_upload_path("../../evil.sh")
        self.assertEqual(ctx.exception.status_code, 415)

        fake = self.manager.new_upload_path("fake.mp4")
        self.assertEqual(fake.parent, Path(self.tmp.name))
        fake.write_bytes(b"this is not a video")
        with self.assertRaises(VideoSourceError) as ctx:
            self.manager.activate_upload(fake, "fake.mp4")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertFalse(fake.exists())
        self.assertEqual(self.manager.mode, SOURCE_DEFAULT)

    def test_browser_frames_only_accepted_in_browser_mode(self) -> None:
        with self.assertRaises(VideoSourceError) as ctx:
            self.manager.push_browser_frame(jpeg_bytes())
        self.assertEqual(ctx.exception.status_code, 409)

        self.manager.select(SOURCE_BROWSER)
        self.reader._apply_pending_switch()
        with self.assertRaises(VideoSourceError) as ctx:
            self.manager.push_browser_frame(b"not an image")
        self.assertEqual(ctx.exception.status_code, 422)
        self.manager.push_browser_frame(jpeg_bytes())
        self.assertIsNotNone(self.reader._pushed_frame)


class TestSourceRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.reader = CameraStreamReader(
            "test", stream_url="0", target_width=320, target_height=180
        )
        self.manager = VideoSourceManager(self.reader, self.tmp.name)
        app = FastAPI()
        app.state.pipeline_engine = SimpleNamespace(video_sources=self.manager)
        app.include_router(source_router)
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {make_token()}"}

    def tearDown(self) -> None:
        self.reader.stop()
        self.tmp.cleanup()

    def test_reading_is_public_but_changes_need_a_valid_operator_token(self) -> None:
        self.assertEqual(self.client.get("/sources/current").status_code, 200)

        body = {"mode": "browser"}
        self.assertEqual(self.client.post("/sources/select", json=body).status_code, 401)
        for token, expected in (
            ("garbage", 401),
            (make_token(token_type="refresh"), 401),
            (make_token(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), 401),
            (make_token(role="VIEWER"), 403),
        ):
            res = self.client.post(
                "/sources/select",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(res.status_code, expected, token)
        self.assertEqual(self.manager.mode, SOURCE_DEFAULT)

        res = self.client.post("/sources/select", json=body, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["mode"], SOURCE_BROWSER)

        self.assertEqual(
            self.client.post(
                "/sources/select", json={"mode": "other"}, headers=self.headers
            ).status_code,
            422,
        )

    def test_upload_video_then_status_reports_it(self) -> None:
        video = Path(self.tmp.name) / "source.avi"
        write_test_video(video)
        content = video.read_bytes()

        anon = self.client.post("/sources/video?filename=a.avi", content=content)
        self.assertEqual(anon.status_code, 401)

        res = self.client.post(
            "/sources/video?filename=lobby.avi", content=content, headers=self.headers
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["mode"], SOURCE_VIDEO)
        self.assertEqual(res.json()["uploaded_video"], "lobby.avi")
        self.assertEqual(
            self.client.get("/sources/current").json()["uploaded_video"], "lobby.avi"
        )

    def test_upload_rejections_leave_no_files_behind(self) -> None:
        cases = (
            ("run.exe", b"abc", 415),
            ("empty.mp4", b"", 400),
            ("fake.mp4", b"not a video", 422),
        )
        for filename, content, expected in cases:
            res = self.client.post(
                f"/sources/video?filename={filename}",
                content=content,
                headers=self.headers,
            )
            self.assertEqual(res.status_code, expected, filename)
        with mock.patch.object(settings, "VIDEO_UPLOAD_MAX_MB", 0):
            res = self.client.post(
                "/sources/video?filename=big.mp4", content=b"abc", headers=self.headers
            )
        self.assertEqual(res.status_code, 413)
        self.assertEqual(list(Path(self.tmp.name).glob("upload_*")), [])
        self.assertEqual(self.manager.mode, SOURCE_DEFAULT)

    def test_browser_frame_push(self) -> None:
        frame = jpeg_bytes()
        self.assertEqual(
            self.client.post("/sources/browser/frame", content=frame).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/sources/browser/frame", content=frame, headers=self.headers
            ).status_code,
            409,
        )
        self.client.post(
            "/sources/select", json={"mode": "browser"}, headers=self.headers
        )
        self.reader._apply_pending_switch()
        res = self.client.post(
            "/sources/browser/frame", content=frame, headers=self.headers
        )
        self.assertEqual(res.status_code, 204)
        self.assertIsNotNone(self.reader._pushed_frame)


if __name__ == "__main__":
    unittest.main()
