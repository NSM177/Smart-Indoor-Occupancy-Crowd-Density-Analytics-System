"""
Offline Video Test Runner (`scripts/run_video_demo.py`).
Allows testing the complete AI Engine on a PC using any `.mp4` video file
(or generates a realistic multi-zone moving test video if no video file is provided)
before deploying to Raspberry Pi 4/5.

Usage:
    python scripts/run_video_demo.py --video path/to/video.mp4 --max-frames 60
    python scripts/run_video_demo.py --max-frames 45
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.services.pipeline_engine import VisionPipelineEngine
from app.vision.annotator import FrameAnnotator

setup_logging()
logger = get_logger("ai.video_demo")


def ensure_sample_video(video_path: Path, num_frames: int = 60) -> Path:
    """Create a sample `.mp4` video file if the user has not supplied one yet."""
    if video_path.exists():
        return video_path

    video_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 15.0, (width, height))

    for i in range(num_frames):
        frame = np.full((height, width, 3), (35, 40, 50), dtype=np.uint8)
        cv2.putText(
            frame,
            f"Test Video Frame #{i + 1}/{num_frames}",
            (40, 680),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (200, 210, 225),
            2,
            cv2.LINE_AA,
        )
        writer.write(frame)

    writer.release()
    logger.info("Created test video file at %s", video_path)
    return video_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run AI Vision Engine on a video file for PC testing"
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(PROJECT_ROOT / "outputs" / "sample_input.mp4"),
        help="Path to input .mp4 video file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "outputs" / "annotated_output.mp4"),
        help="Path to save annotated output .mp4 video",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=30,
        help="Maximum frames to process in demo run",
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=2,
        help="Frame skip factor (e.g. 2 = run YOLO every 2nd frame)",
    )
    args = parser.parse_args()

    input_path = ensure_sample_video(
        Path(args.video), num_frames=args.max_frames
    )
    settings.CAMERA_SOURCE = str(input_path)
    settings.FRAME_SKIP = max(1, args.frame_skip)

    engine = VisionPipelineEngine(settings=settings)
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        logger.error("Could not open video file: %s", input_path)
        return 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, 15.0, (1280, 720))

    processed = 0
    while processed < args.max_frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frame = cv2.resize(frame, (1280, 720))
        telemetry = engine.process_single_frame(frame, is_hw_connected=True)

        annotated = FrameAnnotator.annotate(
            frame=frame,
            tracks=telemetry.tracks,
            zones=engine.config.zones,
            zone_telemetries=telemetry.zones,
            heatmap_gen=engine.heatmap,
            fps=telemetry.fps,
            room_name=telemetry.roomName,
            virtual_lines=engine.config.virtualLines,
            line_stats=telemetry.lineCounts,
            active_alerts=telemetry.activeAlerts,
            performance=telemetry.performance,
            overlay_zones=True,
            overlay_heatmap=True,
        )
        writer.write(annotated)
        processed += 1

    cap.release()
    writer.release()

    heatmap_file = engine.save_current_heatmap()
    perf = engine._latest_performance
    logger.info(
        "Completed processing %d frames | Avg FPS: %.1f | Inference: %.2f ms | Processing: %.2f ms",
        processed,
        perf.fps,
        perf.inferenceTimeMs,
        perf.processingTimeMs,
    )
    logger.info("Saved annotated video to: %s", out_path.resolve())
    logger.info("Saved density heatmap PNG to: %s", heatmap_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
