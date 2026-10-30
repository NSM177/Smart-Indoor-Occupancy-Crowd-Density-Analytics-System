"""
Vision Pipeline Engine (`pipeline_engine.py`).
Coordinates all modular Computer Vision components:
1. CameraStreamReader (`camera_manager.py`)
2. PersonDetector (`detector.py` - YOLO nano / ONNX)
3. ByteTracker (`tracker.py` - Two-stage ByteTrack multi-object tracking)
4. PeopleCounter (`counter.py` - Virtual line IN/OUT crossing & unique ID state machine)
5. ZoneAnalyzer (`zone_analyzer.py` - Point-in-Polygon & calibrated density people/m²)
6. HeatmapGenerator (`heatmap_generator.py` - Gaussian kernel accumulation & image export)
7. CrowdAlertEngine (`crowd_alert.py` - Hysteresis & sustain duration alerting)
8. PerformanceProfiler (`performance.py` - Frame skipping, FPS, inference_ms, processing_ms)
9. FrameAnnotator (`annotator.py`)
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
import httpx
import numpy as np

from app.core.config import AiServiceSettings
from app.core.logger import get_logger
from app.schemas.vision_schema import (
    CameraConfig,
    EdgeCrowdAlert,
    LineCrossingStats,
    NormalizedPoint,
    PerformanceMetrics,
    RoomVisionConfig,
    TrackedPerson,
    VirtualLineConfig,
    VisionTelemetryPayload,
    ZoneConfig,
    ZoneTelemetry,
)
from app.services.mqtt_publisher import AiMqttBridge
from app.vision.annotator import FrameAnnotator
from app.vision.camera_manager import CameraStreamReader
from app.vision.counter import PeopleCounter
from app.vision.crowd_alert import CrowdAlertEngine
from app.vision.detector import PersonDetector
from app.vision.heatmap_generator import HeatmapGenerator
from app.vision.performance import PerformanceProfiler
from app.vision.tracker import ByteTracker
from app.vision.zone_analyzer import ZoneAnalyzer

logger = get_logger("ai.pipeline_engine")


class VisionPipelineEngine:
    """Orchestrates the real-time computer vision and crowd analytics pipeline."""

    def __init__(self, settings: AiServiceSettings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Load initial JSON configuration from `config/zones.json`
        self.config: RoomVisionConfig = (
            ZoneAnalyzer.load_config_from_json(settings.ZONES_CONFIG_PATH)
            or RoomVisionConfig()
        )

        self.camera_reader = CameraStreamReader(
            camera_id="default",
            stream_url=settings.CAMERA_SOURCE,
            target_width=settings.FRAME_WIDTH,
            target_height=settings.FRAME_HEIGHT,
            target_fps=settings.TARGET_FPS,
        )

        self.detector = PersonDetector(
            model_path=settings.YOLO_MODEL_PATH,
            conf_threshold=settings.YOLO_CONFIDENCE_THRESHOLD,
            low_conf_threshold=settings.YOLO_LOW_CONFIDENCE_THRESHOLD,
            iou_threshold=settings.YOLO_IOU_THRESHOLD,
            inference_size=(
                settings.INFERENCE_WIDTH,
                settings.INFERENCE_HEIGHT,
            ),
        )

        self.tracker = ByteTracker(
            high_thresh=settings.YOLO_CONFIDENCE_THRESHOLD,
            low_thresh=settings.YOLO_LOW_CONFIDENCE_THRESHOLD,
            match_iou_thresh=settings.BYTETRACK_MATCH_THRESH,
            track_buffer=settings.BYTETRACK_TRACK_BUFFER,
        )

        self.counter = PeopleCounter(debounce_sec=2.0)

        self.heatmap = HeatmapGenerator(
            grid_width=settings.HEATMAP_GRID_WIDTH,
            grid_height=settings.HEATMAP_GRID_HEIGHT,
            decay_factor=settings.HEATMAP_DECAY_FACTOR,
        )

        self.alert_engine = CrowdAlertEngine(
            hysteresis_ratio=settings.ALERT_HYSTERESIS_RATIO,
            sustain_sec=settings.ALERT_SUSTAIN_SEC,
        )

        self.profiler = PerformanceProfiler(
            frame_skip=settings.FRAME_SKIP,
            inference_resolution=(
                settings.INFERENCE_WIDTH,
                settings.INFERENCE_HEIGHT,
            ),
        )

        self.mqtt_bridge = AiMqttBridge(
            settings=settings,
            on_config_update=self.apply_config_dict,
        )

        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_tracks: List[TrackedPerson] = []
        self._latest_zone_telemetries: List[ZoneTelemetry] = []
        self._latest_line_stats: List[LineCrossingStats] = []
        self._latest_alerts: List[EdgeCrowdAlert] = []
        self._latest_performance: PerformanceMetrics = (
            self.profiler.get_metrics(self.detector.backend_name)
        )
        self._latest_telemetry_payload: Optional[VisionTelemetryPayload] = None

    def start(self) -> None:
        self.mqtt_bridge.start()
        self.camera_reader.start()
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._pipeline_loop,
            daemon=True,
            name="VisionPipelineWorker",
        )
        self._worker_thread.start()
        logger.info("Vision Pipeline Engine started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self.camera_reader.stop()
        self.mqtt_bridge.stop()
        logger.info("Vision Pipeline Engine stopped.")

    def apply_config_dict(self, raw_data: Dict[str, Any]) -> RoomVisionConfig:
        """Parse and apply dynamic Room, Camera, Virtual Line, and Polygon Zone config."""
        with self._lock:
            room_id = str(
                raw_data.get("roomCode")
                or raw_data.get("roomId")
                or raw_data.get("code")
                or raw_data.get("id")
                or self.config.roomId
            )
            room_name = str(
                raw_data.get("roomName")
                or raw_data.get("name")
                or self.config.roomName
            )
            area_sqm = float(
                raw_data.get("areaSqm")
                or raw_data.get("area_sqm")
                or self.config.areaSqm
            )
            max_capacity = int(
                raw_data.get("maxCapacity")
                or raw_data.get("max_capacity")
                or self.config.maxCapacity
            )

            cameras_raw = raw_data.get("cameras") or []
            cameras: List[CameraConfig] = []
            for c in cameras_raw:
                cameras.append(
                    CameraConfig(
                        id=str(c.get("id", "default")),
                        name=str(c.get("name", "Camera")),
                        streamUrl=str(c.get("streamUrl", "0")),
                        frameWidth=int(c.get("frameWidth", 1280)),
                        frameHeight=int(c.get("frameHeight", 720)),
                        targetFps=int(c.get("targetFps", 15)),
                        isActive=bool(c.get("isActive", True)),
                    )
                )

            zones_raw = raw_data.get("zones") or []
            zones: List[ZoneConfig] = []
            for z in zones_raw:
                pts_raw = (
                    z.get("polygonPoints")
                    or z.get("polygonCoordinates")
                    or z.get("polygon_coordinates")
                    or []
                )
                pts = [
                    NormalizedPoint(
                        x=min(1.0, max(0.0, float(p.get("x", 0.0)))),
                        y=min(1.0, max(0.0, float(p.get("y", 0.0)))),
                    )
                    for p in pts_raw
                    if isinstance(p, dict)
                ]
                if len(pts) < 3:
                    continue
                zones.append(
                    ZoneConfig(
                        id=str(z.get("id")),
                        name=str(z.get("name", "Zone")),
                        code=str(z.get("code", "ZONE")),
                        polygonPoints=pts,
                        areaSqm=float(
                            z.get("areaSqm") or z.get("area_sqm") or 25.0
                        ),
                        maxCapacity=int(
                            z.get("maxCapacity") or z.get("max_capacity") or 15
                        ),
                        warningDensityThreshold=float(
                            z.get("warningDensityThreshold")
                            or z.get("warningDensity")
                            or z.get("warning_density")
                            or 0.35
                        ),
                        criticalDensityThreshold=float(
                            z.get("criticalDensityThreshold")
                            or z.get("criticalDensity")
                            or z.get("critical_density")
                            or 0.50
                        ),
                        colorHex=str(
                            z.get("colorHex") or z.get("color_hex") or "#3B82F6"
                        ),
                        isActive=bool(z.get("isActive", True)),
                    )
                )

            vlines_raw = raw_data.get("virtualLines")
            vlines: List[VirtualLineConfig] = list(self.config.virtualLines)
            if isinstance(vlines_raw, list):
                vlines = []
                for vl in vlines_raw:
                    vlines.append(
                        VirtualLineConfig(
                            id=str(vl.get("id", "line-1")),
                            name=str(vl.get("name", "Entrance Gate")),
                            start=NormalizedPoint(
                                x=float(vl["start"]["x"]),
                                y=float(vl["start"]["y"]),
                            ),
                            end=NormalizedPoint(
                                x=float(vl["end"]["x"]),
                                y=float(vl["end"]["y"]),
                            ),
                            inDirection=vl.get("inDirection", "DOWN"),
                        )
                    )

            parsed_config = RoomVisionConfig(
                roomId=room_id,
                roomName=room_name,
                areaSqm=area_sqm,
                maxCapacity=max_capacity,
                cameras=cameras,
                zones=zones if zones else self.config.zones,
                virtualLines=vlines,
            )
            self.config = parsed_config

            if cameras:
                primary_cam = cameras[0]
                self.camera_reader.camera_id = primary_cam.id
                self.camera_reader.update_source(
                    stream_url=primary_cam.streamUrl,
                    target_width=primary_cam.frameWidth,
                    target_height=primary_cam.frameHeight,
                    target_fps=primary_cam.targetFps,
                )

            logger.info(
                "Updated Vision Config for room '%s' (%s): %d zone(s), %d virtual line(s)",
                room_name,
                room_id,
                len(self.config.zones),
                len(self.config.virtualLines),
            )
            return parsed_config

    def try_sync_from_backend(self) -> bool:
        """Fetch active Room/Camera/Zone configuration from NestJS Backend API if reachable."""
        url = f"{self.settings.BACKEND_INTERNAL_URL.rstrip('/')}/rooms"
        try:
            with httpx.Client(timeout=2.5) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    rooms = resp.json()
                    if isinstance(rooms, list) and len(rooms) > 0:
                        self.apply_config_dict(rooms[0])
                        return True
        except Exception:
            pass
        return False

    def process_single_frame(
        self, frame: np.ndarray, is_hw_connected: bool = True
    ) -> VisionTelemetryPayload:
        """
        Run the complete 7-stage Computer Vision pipeline on a single BGR frame.
        Can be called directly by the real-time camera loop or by offline video/unit tests.
        """
        t_proc_start = time.perf_counter()
        height, width = frame.shape[:2]
        inference_ms = 0.0

        if is_hw_connected:
            if self.profiler.should_run_detection():
                detections, inference_ms = self.detector.detect(
                    frame, return_low_conf_for_bytetrack=True
                )
                tracks = self.tracker.update(detections, width, height)
            else:
                tracks = self.tracker.predict_only(width, height)
        else:
            tracks = []

        with self._lock:
            cfg = self.config

        # 1. Virtual Line People Counting (IN / OUT)
        line_stats = self.counter.update(
            tracks=tracks,
            tracker=self.tracker,
            virtual_lines=cfg.virtualLines,
            frame_width=width,
            frame_height=height,
        )

        # 2. Polygon Zone Point-in-Polygon & Calibrated Density Analysis
        tracks, zone_telemetries = ZoneAnalyzer.analyze_zones(
            tracks=tracks,
            zones=cfg.zones,
            frame_width=width,
            frame_height=height,
        )

        # 3. Gaussian Spatial Density Heatmap Update
        self.heatmap.update(tracks)

        # 4. Room-level Density & Crowd Alert Evaluation with Hysteresis
        total_count = len(tracks)
        room_density = (
            round(total_count / float(cfg.areaSqm), 4)
            if cfg.areaSqm > 0
            else 0.0
        )
        room_occ_rate = (
            round((total_count / float(cfg.maxCapacity)) * 100.0, 1)
            if cfg.maxCapacity > 0
            else 0.0
        )
        room_level = ZoneAnalyzer.classify_density_level(
            room_density,
            cfg.warningDensityThreshold,
            cfg.criticalDensityThreshold,
        )

        active_alerts = self.alert_engine.evaluate(
            room_id=cfg.roomId,
            room_name=cfg.roomName,
            total_count=total_count,
            room_max_capacity=cfg.maxCapacity,
            room_density=room_density,
            room_warn_density=cfg.warningDensityThreshold,
            room_crit_density=cfg.criticalDensityThreshold,
            zones=zone_telemetries,
        )

        # 5. Record Performance Metrics
        processing_ms = round((time.perf_counter() - t_proc_start) * 1000.0, 2)
        perf_metrics = self.profiler.record_frame(
            inference_ms=inference_ms, processing_ms=processing_ms
        )
        perf_metrics.modelBackend = self.detector.backend_name

        camera_id = (
            cfg.cameras[0].id
            if cfg.cameras
            else self.camera_reader.camera_id
        )

        telemetry = VisionTelemetryPayload(
            timestamp=datetime.now(timezone.utc).isoformat(),
            roomId=cfg.roomId,
            roomName=cfg.roomName,
            cameraId=camera_id,
            fps=perf_metrics.fps,
            totalCount=total_count,
            roomAreaSqm=cfg.areaSqm,
            roomMaxCapacity=cfg.maxCapacity,
            roomDensity=room_density,
            roomOccupancyRate=room_occ_rate,
            roomDensityLevel=room_level,
            lineCounts=line_stats,
            tracks=tracks,
            zones=zone_telemetries,
            activeAlerts=active_alerts,
            performance=perf_metrics,
            heatmapGrid=self.heatmap.get_normalized_grid(),
        )

        with self._lock:
            self._latest_raw_frame = frame
            self._latest_tracks = tracks
            self._latest_zone_telemetries = zone_telemetries
            self._latest_line_stats = line_stats
            self._latest_alerts = active_alerts
            self._latest_performance = perf_metrics
            self._latest_telemetry_payload = telemetry

        return telemetry

    def _pipeline_loop(self) -> None:
        last_backend_sync_ts = 0.0
        backend_synced = False
        last_telemetry_ts = 0.0
        publish_interval = max(
            0.25, float(self.settings.TELEMETRY_PUBLISH_INTERVAL_SEC)
        )

        while not self._stop_event.is_set():
            now_mono = time.monotonic()

            if not backend_synced and (now_mono - last_backend_sync_ts >= 5.0):
                last_backend_sync_ts = now_mono
                backend_synced = self.try_sync_from_backend()

            frame, _cam_fps, is_hw_connected = (
                self.camera_reader.get_latest_frame()
            )
            if frame is None:
                self._stop_event.wait(0.05)
                continue

            telemetry = self.process_single_frame(
                frame=frame, is_hw_connected=is_hw_connected
            )

            if telemetry.roomId and (
                now_mono - last_telemetry_ts >= publish_interval
            ):
                last_telemetry_ts = now_mono
                self.mqtt_bridge.publish_telemetry(
                    telemetry.roomId, telemetry.model_dump()
                )

            self._stop_event.wait(0.03)

    def get_annotated_jpeg(
        self,
        overlay_zones: bool = True,
        overlay_heatmap: bool = False,
    ) -> bytes:
        with self._lock:
            frame = (
                self._latest_raw_frame.copy()
                if self._latest_raw_frame is not None
                else None
            )
            tracks = list(self._latest_tracks)
            zone_telemetries = list(self._latest_zone_telemetries)
            line_stats = list(self._latest_line_stats)
            alerts = list(self._latest_alerts)
            perf = self._latest_performance
            zones = list(self.config.zones)
            vlines = list(self.config.virtualLines)
            room_name = self.config.roomName

        if frame is None:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        annotated = FrameAnnotator.annotate(
            frame=frame,
            tracks=tracks,
            zones=zones,
            zone_telemetries=zone_telemetries,
            heatmap_gen=self.heatmap,
            fps=perf.fps,
            room_name=room_name,
            virtual_lines=vlines,
            line_stats=line_stats,
            active_alerts=alerts,
            performance=perf,
            overlay_zones=overlay_zones,
            overlay_heatmap=overlay_heatmap,
        )
        ok, encoded = cv2.imencode(
            ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82]
        )
        return encoded.tobytes() if ok else b""

    def save_current_heatmap(self, custom_path: Optional[str] = None) -> str:
        with self._lock:
            bg = (
                self._latest_raw_frame.copy()
                if self._latest_raw_frame is not None
                else None
            )
        target = custom_path or self.settings.HEATMAP_SAVE_DIR
        return self.heatmap.save_image(target, background_frame=bg)

    def get_status(self) -> Dict[str, Any]:
        _, cam_fps, hw_connected = self.camera_reader.get_latest_frame()
        perf = self._latest_performance
        return {
            "status": "ok",
            "service": "smart-occupancy-ai-service",
            "yoloReady": self.detector.is_ready,
            "yoloModel": self.settings.YOLO_MODEL_PATH,
            "modelBackend": self.detector.backend_name,
            "mqttConnected": self.mqtt_bridge.is_connected,
            "cameraHardwareConnected": hw_connected,
            "cameraStreamUrl": self.camera_reader.stream_url,
            "fps": perf.fps or cam_fps,
            "inferenceTimeMs": perf.inferenceTimeMs,
            "processingTimeMs": perf.processingTimeMs,
            "frameSkip": perf.frameSkip,
            "inferenceResolution": perf.inferenceResolution,
            "configuredRoomId": self.config.roomId,
            "activeZonesCount": len(
                [z for z in self.config.zones if z.isActive]
            ),
            "virtualLinesCount": len(self.config.virtualLines),
            "totalUniqueVisitors": self.counter.total_unique_visitors,
        }
