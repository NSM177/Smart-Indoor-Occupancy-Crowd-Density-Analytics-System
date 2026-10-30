"""
Main Entrypoint for the Smart Indoor Occupancy & Crowd Density AI Engine (`main.py`).
Supports:
- FastAPI server mode (`python -m app.main`)
- Custom camera / video input (`python -m app.main --source data/test_crowd.mp4`)
- Raspberry Pi performance flags (`--frame-skip 2 --inference-width 640 --inference-height 384`)
- ONNX model export (`python -m app.main --export-onnx`)
- Standalone verification mode (`python -m app.main --self-test`)
"""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import tempfile
from typing import AsyncGenerator

import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as vision_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.schemas.vision_schema import (
    NormalizedPoint,
    RawDetection,
    VirtualLineConfig,
    ZoneConfig,
)
from app.services.pipeline_engine import VisionPipelineEngine
from app.vision.annotator import FrameAnnotator
from app.vision.counter import PeopleCounter
from app.vision.crowd_alert import CrowdAlertEngine
from app.vision.detector import PersonDetector
from app.vision.heatmap_generator import HeatmapGenerator
from app.vision.performance import PerformanceProfiler
from app.vision.tracker import ByteTracker
from app.vision.zone_analyzer import ZoneAnalyzer

setup_logging()
logger = get_logger("ai.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    engine = VisionPipelineEngine(settings=settings)
    app.state.pipeline_engine = engine
    engine.start()
    yield
    engine.stop()


app = FastAPI(
    title="Smart Indoor Occupancy & Crowd Density AI Vision Service",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vision_router)


def run_vision_self_test() -> int:
    """Verify ByteTracker, PeopleCounter (Virtual Line), ZoneAnalyzer, Heatmap, and CrowdAlert."""
    logger.info("Running AI Vision Engine comprehensive self-test...")
    width, height = 1280, 720
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    # 1. Test ByteTracker (Two-stage association + occlusion recovery)
    tracker = ByteTracker(
        high_thresh=0.35, low_thresh=0.15, match_iou_thresh=0.25, track_buffer=10
    )
    dets_f1 = [
        RawDetection(bbox=(200, 200, 260, 340), confidence=0.88),
        RawDetection(bbox=(300, 220, 360, 380), confidence=0.82),
    ]
    tracks_f1 = tracker.update(dets_f1, width, height)
    assert len(tracks_f1) == 2

    # Frame 2: Person 1 moves across virtual line y=360 (foot goes from 340 -> 390)
    # Person 2 is partially occluded (confidence drops to 0.20 -> ByteTrack Stage 2)
    dets_f2 = [
        RawDetection(bbox=(200, 250, 260, 390), confidence=0.85),
        RawDetection(bbox=(302, 222, 362, 382), confidence=0.20),
    ]
    tracks_f2 = tracker.update(dets_f2, width, height)
    assert len(tracks_f2) == 2
    assert {t.id for t in tracks_f1} == {t.id for t in tracks_f2}

    # 2. Test Virtual Line People Counter (IN / OUT)
    vlines = [
        VirtualLineConfig(
            id="line-gate-1",
            name="Entrance Gate",
            start=NormalizedPoint(x=0.05, y=0.50),  # y = 360px
            end=NormalizedPoint(x=0.45, y=0.50),
            inDirection="DOWN",
        )
    ]
    counter = PeopleCounter(debounce_sec=1.0)
    line_stats = counter.update(tracks_f2, tracker, vlines, width, height)
    assert len(line_stats) == 1
    assert line_stats[0].inCount == 1 and line_stats[0].outCount == 0

    # 3. Test ZoneAnalyzer (Point-in-Polygon & calibrated density people/m²)
    zones = [
        ZoneConfig(
            id="zone-a",
            name="Zone A",
            code="ZONE_A",
            polygonPoints=[
                NormalizedPoint(x=0.05, y=0.10),
                NormalizedPoint(x=0.45, y=0.10),
                NormalizedPoint(x=0.45, y=0.90),
                NormalizedPoint(x=0.05, y=0.90),
            ],
            areaSqm=10.0,
            maxCapacity=4,
            warningDensityThreshold=0.15,
            criticalDensityThreshold=0.30,
            colorHex="#3B82F6",
            isActive=True,
        )
    ]
    tracks_f2, zone_telemetries = ZoneAnalyzer.analyze_zones(
        tracks=tracks_f2,
        zones=zones,
        frame_width=width,
        frame_height=height,
    )
    assert zone_telemetries[0].count == 2
    assert zone_telemetries[0].density == 0.2

    # 4. Test CrowdAlertEngine with Hysteresis
    alert_engine = CrowdAlertEngine(hysteresis_ratio=0.10, sustain_sec=0.0)
    alerts = alert_engine.evaluate(
        room_id="room-1",
        room_name="Test Room",
        total_count=2,
        room_max_capacity=20,
        room_density=0.05,
        room_warn_density=0.35,
        room_crit_density=0.50,
        zones=zone_telemetries,
        now_mono=100.0,
    )
    assert len(alerts) == 1
    assert alerts[0].severity == "WARNING"

    # 5. Test HeatmapGenerator & disk export
    heatmap = HeatmapGenerator(grid_width=64, grid_height=36, decay_factor=0.96)
    heatmap.update(tracks_f2)
    with tempfile.TemporaryDirectory() as tmpdir:
        saved_file = heatmap.save_image(tmpdir, background_frame=frame)
        assert Path(saved_file).exists()

    # 6. Test PerformanceProfiler & FrameAnnotator
    profiler = PerformanceProfiler(frame_skip=2, inference_resolution=(640, 384))
    perf = profiler.record_frame(inference_ms=14.2, processing_ms=18.5)
    annotated = FrameAnnotator.annotate(
        frame=frame,
        tracks=tracks_f2,
        zones=zones,
        zone_telemetries=zone_telemetries,
        heatmap_gen=heatmap,
        fps=perf.fps,
        room_name="Self-Test Room",
        virtual_lines=vlines,
        line_stats=line_stats,
        active_alerts=alerts,
        performance=perf,
        overlay_zones=True,
        overlay_heatmap=True,
    )
    assert annotated.shape == (height, width, 3)

    logger.info("AI Vision Engine comprehensive self-test PASSED.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Smart Indoor Occupancy & Crowd Density AI Vision Engine"
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Camera index ('0'), 'picamera', RTSP URL, or video file path (.mp4)",
    )
    parser.add_argument(
        "--zones-json",
        type=str,
        default=None,
        help="Path to zones configuration JSON file (default: config/zones.json)",
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=None,
        help="Run YOLO detection every Nth frame (e.g. 2 or 3 for Raspberry Pi)",
    )
    parser.add_argument(
        "--inference-width",
        type=int,
        default=None,
        help="Downscaled width for YOLO inference (default: 640)",
    )
    parser.add_argument(
        "--inference-height",
        type=int,
        default=None,
        help="Downscaled height for YOLO inference (default: 384)",
    )
    parser.add_argument(
        "--export-onnx",
        action="store_true",
        help="Export the configured YOLO .pt model to .onnx for Raspberry Pi and exit",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run standalone vision algorithms verification and exit",
    )
    args = parser.parse_args()

    if args.source is not None:
        settings.CAMERA_SOURCE = args.source
    if args.zones_json is not None:
        settings.ZONES_CONFIG_PATH = args.zones_json
    if args.frame_skip is not None:
        settings.FRAME_SKIP = max(1, args.frame_skip)
    if args.inference_width is not None:
        settings.INFERENCE_WIDTH = args.inference_width
    if args.inference_height is not None:
        settings.INFERENCE_HEIGHT = args.inference_height

    if args.self_test:
        sys.exit(run_vision_self_test())

    if args.export_onnx:
        detector = PersonDetector(
            model_path=settings.YOLO_MODEL_PATH,
            inference_size=(settings.INFERENCE_WIDTH, settings.INFERENCE_HEIGHT),
        )
        onnx_path = detector.export_to_onnx(
            imgsz=(settings.INFERENCE_WIDTH, settings.INFERENCE_HEIGHT)
        )
        sys.exit(0 if onnx_path else 1)

    uvicorn.run(
        "app.main:app",
        host=settings.AI_SERVICE_HOST,
        port=settings.AI_SERVICE_PORT,
        reload=False,
    )
