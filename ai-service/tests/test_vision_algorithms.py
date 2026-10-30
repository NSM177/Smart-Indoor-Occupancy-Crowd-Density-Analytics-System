"""
Unit Test Suite for Smart Indoor Occupancy & Crowd Density AI Engine.
Tests:
1. ByteTrack Multi-Object Tracking (Two-stage association & occlusion recovery)
2. Virtual Line Crossing People Counter (IN / OUT & anti-double-counting state machine)
3. Polygon Zone Point-in-Polygon & Calibrated Crowd Density (people / m²)
4. Gaussian Spatial Density Heatmap (Accumulation, decay & image export)
5. Crowd Alert Engine (Hysteresis & sustain duration timer)
6. Performance Profiler & Frame Skipping
7. FastAPI REST Endpoints (/health, /analytics/current, /analytics/zones, /heatmap/save)
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.vision_schema import (
    NormalizedPoint,
    RawDetection,
    TrackedPerson,
    VirtualLineConfig,
    ZoneConfig,
)
from app.vision.counter import PeopleCounter, segments_intersect
from app.vision.crowd_alert import CrowdAlertEngine
from app.vision.heatmap_generator import HeatmapGenerator
from app.vision.performance import PerformanceProfiler
from app.vision.tracker import ByteTracker, compute_iou_matrix
from app.vision.zone_analyzer import ZoneAnalyzer


class TestVisionAlgorithms(unittest.TestCase):
    """Unit tests for the core Computer Vision and Crowd Analytics algorithms."""

    def test_iou_matrix_computation(self) -> None:
        boxes_a = np.array([[0, 0, 100, 100], [200, 200, 300, 300]])
        boxes_b = np.array([[0, 0, 100, 100], [50, 50, 150, 150]])
        iou = compute_iou_matrix(boxes_a, boxes_b)
        self.assertEqual(iou.shape, (2, 2))
        self.assertAlmostEqual(float(iou[0, 0]), 1.0, places=4)
        # Intersection of [0,0,100,100] and [50,50,150,150] is 50x50=2500; Union = 10000+10000-2500=17500
        self.assertAlmostEqual(float(iou[0, 1]), 2500.0 / 17500.0, places=4)
        self.assertAlmostEqual(float(iou[1, 0]), 0.0, places=4)

    def test_bytetrack_two_stage_association_and_occlusion_recovery(self) -> None:
        tracker = ByteTracker(
            high_thresh=0.40,
            low_thresh=0.15,
            match_iou_thresh=0.25,
            second_match_iou_thresh=0.20,
            track_buffer=5,
        )

        # Frame 1: Two high-confidence detections
        f1 = [
            RawDetection(bbox=(100, 100, 160, 260), confidence=0.85),
            RawDetection(bbox=(400, 150, 460, 310), confidence=0.80),
        ]
        t1 = tracker.update(f1, 1280, 720)
        self.assertEqual(len(t1), 2)
        ids_f1 = {p.id for p in t1}
        self.assertEqual(ids_f1, {1, 2})

        # Frame 2: Track #2 is partially occluded -> confidence drops to 0.22 (in D_low)
        f2 = [
            RawDetection(bbox=(105, 102, 165, 262), confidence=0.86),
            RawDetection(bbox=(404, 152, 464, 312), confidence=0.22),
        ]
        t2 = tracker.update(f2, 1280, 720)
        self.assertEqual(len(t2), 2)
        self.assertEqual({p.id for p in t2}, {1, 2})

        # Frame 3: Track #2 is completely occluded (0 detections for Track #2)
        f3 = [RawDetection(bbox=(110, 104, 170, 264), confidence=0.88)]
        t3 = tracker.update(f3, 1280, 720)
        self.assertEqual(len(t3), 1)
        self.assertEqual(t3[0].id, 1)

        # Frame 4: Track #2 re-emerges from occlusion -> recovers original ID #2 (no double counting!)
        f4 = [
            RawDetection(bbox=(115, 106, 175, 266), confidence=0.87),
            RawDetection(bbox=(410, 155, 470, 315), confidence=0.79),
        ]
        t4 = tracker.update(f4, 1280, 720)
        self.assertEqual(len(t4), 2)
        self.assertEqual({p.id for p in t4}, {1, 2})

    def test_virtual_line_crossing_and_anti_double_count(self) -> None:
        self.assertTrue(
            segments_intersect((0, 100), (200, 100), (100, 50), (100, 150))
        )
        self.assertFalse(
            segments_intersect((0, 100), (200, 100), (100, 20), (100, 80))
        )

        tracker = ByteTracker(high_thresh=0.35, low_thresh=0.15)
        counter = PeopleCounter(debounce_sec=0.0)
        vline = VirtualLineConfig(
            id="gate-1",
            name="Main Gate",
            start=NormalizedPoint(x=0.0, y=0.5),  # y = 360 in 1280x720
            end=NormalizedPoint(x=1.0, y=0.5),
            inDirection="DOWN",
        )

        # Frame 1: Person foot above line (y2 = 345)
        t1 = tracker.update(
            [RawDetection(bbox=(200, 185, 260, 345), confidence=0.90)],
            1280,
            720,
        )
        s1 = counter.update(t1, tracker, [vline], 1280, 720)
        self.assertEqual(s1[0].inCount, 0)
        self.assertEqual(s1[0].outCount, 0)

        # Frame 2: Person crosses line downward (y2 = 375) -> IN = 1
        t2 = tracker.update(
            [RawDetection(bbox=(200, 215, 260, 375), confidence=0.90)],
            1280,
            720,
        )
        s2 = counter.update(t2, tracker, [vline], 1280, 720)
        self.assertEqual(s2[0].inCount, 1)
        self.assertEqual(s2[0].outCount, 0)

        # Frame 3: Person pauses just below the line (y2 = 372) -> still IN = 1
        t3 = tracker.update(
            [RawDetection(bbox=(200, 212, 260, 372), confidence=0.90)],
            1280,
            720,
        )
        s3 = counter.update(t3, tracker, [vline], 1280, 720)
        self.assertEqual(s3[0].inCount, 1)

        # Frame 4: Person steps back upward across the line (y2 = 340) -> OUT = 1
        t4 = tracker.update(
            [RawDetection(bbox=(200, 180, 260, 340), confidence=0.90)],
            1280,
            720,
        )
        s4 = counter.update(t4, tracker, [vline], 1280, 720)
        self.assertEqual(s4[0].inCount, 1)
        self.assertEqual(s4[0].outCount, 1)
        self.assertEqual(s4[0].netFlow, 0)

    def test_polygon_zone_density_and_json_config(self) -> None:
        cfg = ZoneAnalyzer.load_config_from_json(settings.ZONES_CONFIG_PATH)
        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertGreaterEqual(len(cfg.zones), 3)

        zone_a = ZoneConfig(
            id="z-a",
            name="Zone A",
            code="ZONE_A",
            polygonPoints=[
                NormalizedPoint(x=0.0, y=0.0),
                NormalizedPoint(x=0.5, y=0.0),
                NormalizedPoint(x=0.5, y=1.0),
                NormalizedPoint(x=0.0, y=1.0),
            ],
            areaSqm=25.0,
            maxCapacity=10,
            warningDensityThreshold=0.10,
            criticalDensityThreshold=0.20,
        )

        persons = [
            TrackedPerson(
                id=1,
                bbox=(100, 100, 160, 300),
                confidence=0.9,
                footPoint=NormalizedPoint(x=130 / 1280.0, y=300 / 720.0),
                footPointPx=(130, 300),
                dwellSec=10.0,
            ),
            TrackedPerson(
                id=2,
                bbox=(200, 120, 260, 320),
                confidence=0.85,
                footPoint=NormalizedPoint(x=230 / 1280.0, y=320 / 720.0),
                footPointPx=(230, 320),
                dwellSec=20.0,
            ),
            # Outside Zone A (x = 900 > 640)
            TrackedPerson(
                id=3,
                bbox=(870, 120, 930, 320),
                confidence=0.88,
                footPoint=NormalizedPoint(x=900 / 1280.0, y=320 / 720.0),
                footPointPx=(900, 320),
                dwellSec=5.0,
            ),
        ]

        tracks, z_stats = ZoneAnalyzer.analyze_zones(
            persons, [zone_a], 1280, 720
        )
        self.assertEqual(len(z_stats), 1)
        self.assertEqual(z_stats[0].count, 2)
        # 2 people / 25 m² = 0.08 people/m²
        self.assertAlmostEqual(z_stats[0].density, 0.08, places=4)
        self.assertAlmostEqual(z_stats[0].occupancyRate, 20.0, places=1)
        self.assertAlmostEqual(z_stats[0].avgDwellTimeSec, 15.0, places=1)
        self.assertEqual(tracks[0].zoneCode, "ZONE_A")
        self.assertIsNone(tracks[2].zoneCode)

    def test_heatmap_accumulation_decay_and_save(self) -> None:
        hm = HeatmapGenerator(grid_width=32, grid_height=18, decay_factor=0.90)
        p = TrackedPerson(
            id=1,
            bbox=(600, 300, 680, 500),
            confidence=0.9,
            footPoint=NormalizedPoint(x=0.5, y=0.5),
            footPointPx=(640, 360),
        )
        hm.update([p])
        grid_1 = np.array(hm.get_normalized_grid())
        self.assertGreater(float(np.max(grid_1)), 0.0)

        # Update with empty tracks -> energy decays by 0.90
        raw_max_before = float(np.max(hm._accumulator))
        hm.update([])
        raw_max_after = float(np.max(hm._accumulator))
        self.assertAlmostEqual(raw_max_after, raw_max_before * 0.90, places=4)

        with tempfile.TemporaryDirectory() as tmpdir:
            saved_path = hm.save_image(tmpdir)
            self.assertTrue(Path(saved_path).exists())

    def test_crowd_alert_hysteresis_and_sustain_timer(self) -> None:
        engine = CrowdAlertEngine(hysteresis_ratio=0.20, sustain_sec=2.0)

        # T=0.0s: count=9 exceeds warning threshold (8.0 for max_capacity=10), but sustain_sec=2.0 not reached yet
        alerts_t0 = engine.evaluate(
            room_id="r1",
            room_name="Room 1",
            total_count=9,
            room_max_capacity=10,
            room_density=0.2,
            room_warn_density=0.5,
            room_crit_density=0.8,
            zones=[],
            now_mono=10.0,
        )
        self.assertEqual(len(alerts_t0), 0)

        # T=2.5s (now_mono=12.5): sustained for 2.5s >= 2.0s -> WARNING alert triggers!
        alerts_t1 = engine.evaluate(
            room_id="r1",
            room_name="Room 1",
            total_count=9,
            room_max_capacity=10,
            room_density=0.2,
            room_warn_density=0.5,
            room_crit_density=0.8,
            zones=[],
            now_mono=12.5,
        )
        self.assertEqual(len(alerts_t1), 1)
        self.assertEqual(alerts_t1[0].severity, "WARNING")

        # T=3.5s: count drops slightly to 7 (below warn=8.0, but above clear_thresh = 8.0 * 0.8 = 6.4)
        # Hysteresis keeps the alert ACTIVE!
        alerts_t2 = engine.evaluate(
            room_id="r1",
            room_name="Room 1",
            total_count=7,
            room_max_capacity=10,
            room_density=0.2,
            room_warn_density=0.5,
            room_crit_density=0.8,
            zones=[],
            now_mono=13.5,
        )
        self.assertEqual(len(alerts_t2), 1)

        # T=4.5s: count drops to 6 (< 6.4 clear threshold) -> Alert clears!
        alerts_t3 = engine.evaluate(
            room_id="r1",
            room_name="Room 1",
            total_count=6,
            room_max_capacity=10,
            room_density=0.2,
            room_warn_density=0.5,
            room_crit_density=0.8,
            zones=[],
            now_mono=14.5,
        )
        self.assertEqual(len(alerts_t3), 0)

    def test_performance_profiler_and_frame_skipping(self) -> None:
        prof = PerformanceProfiler(
            frame_skip=3, inference_resolution=(640, 384)
        )
        # Frame 0 -> run detection
        self.assertTrue(prof.should_run_detection())
        prof.record_frame(15.0, 20.0)
        # Frame 1 -> skip detection
        self.assertFalse(prof.should_run_detection())
        prof.record_frame(0.0, 4.0)
        # Frame 2 -> skip detection
        self.assertFalse(prof.should_run_detection())
        prof.record_frame(0.0, 4.0)
        # Frame 3 -> run detection
        self.assertTrue(prof.should_run_detection())
        metrics = prof.record_frame(17.0, 22.0)
        self.assertEqual(metrics.totalFramesProcessed, 4)
        self.assertAlmostEqual(metrics.inferenceTimeMs, 16.0, places=1)

    def test_fastapi_endpoints(self) -> None:
        with TestClient(app) as client:
            r_health = client.get("/health")
            self.assertEqual(r_health.status_code, 200)
            self.assertEqual(r_health.json()["status"], "ok")

            r_curr = client.get("/analytics/current")
            self.assertEqual(r_curr.status_code, 200)
            self.assertIn("totalCount", r_curr.json())
            self.assertIn("lineCounts", r_curr.json())

            r_zones = client.get("/analytics/zones")
            self.assertEqual(r_zones.status_code, 200)
            self.assertIn("zones", r_zones.json())
            self.assertGreaterEqual(r_zones.json()["totalZones"], 3)


if __name__ == "__main__":
    unittest.main()
