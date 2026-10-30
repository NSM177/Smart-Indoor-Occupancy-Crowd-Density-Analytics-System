"""
Module 1: Person Detection Engine (`detector.py`).
Uses YOLO (YOLOv8n / YOLOv11n or exported ONNX runtime) to detect only `Person` (COCO class 0).
Supports resolution downscaling prior to inference for Raspberry Pi 4/5 optimization
and rescaling bounding boxes back to the original camera frame resolution.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.core.logger import get_logger
from app.schemas.vision_schema import RawDetection

logger = get_logger("ai.vision.detector")


class PersonDetector:
    """
    YOLO Person Detector optimized for edge devices (Raspberry Pi 4/5 & PC).
    Filters strictly for COCO class 0 (Person) and supports both PyTorch (.pt)
    and ONNX (.onnx) weights via Ultralytics runtime.
    """

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf_threshold: float = 0.35,
        low_conf_threshold: float = 0.15,
        iou_threshold: float = 0.45,
        inference_size: Tuple[int, int] = (640, 384),
    ) -> None:
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.low_conf_threshold = min(conf_threshold, low_conf_threshold)
        self.iou_threshold = iou_threshold
        self.inference_size = inference_size  # (width, height)

        self._model = None
        self._model_loaded = False
        self._backend_name = "unavailable"
        self.last_inference_ms: float = 0.0

        self._load_model()

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO  # type: ignore

            logger.info("Loading YOLO person detector from '%s'...", self.model_path)
            self._model = YOLO(self.model_path, task="detect")
            self._model_loaded = True
            suffix = Path(self.model_path).suffix.lower()
            self._backend_name = "onnx" if suffix == ".onnx" else "pytorch-ultralytics"
            logger.info(
                "PersonDetector ready (backend=%s, inference_size=%s)",
                self._backend_name,
                self.inference_size,
            )
        except Exception as exc:
            self._model_loaded = False
            self._backend_name = "unloaded"
            logger.warning("Could not load YOLO model '%s': %s", self.model_path, exc)

    @property
    def is_ready(self) -> bool:
        return self._model_loaded and self._model is not None

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def detect(
        self,
        frame: np.ndarray,
        return_low_conf_for_bytetrack: bool = True,
    ) -> Tuple[List[RawDetection], float]:
        """
        Detect persons in a BGR frame.
        If `return_low_conf_for_bytetrack` is True, detections down to `low_conf_threshold`
        are returned so ByteTrack's second stage can associate partially occluded people.

        Returns:
            (detections, inference_time_ms)
        """
        if frame is None or frame.size == 0 or not self.is_ready:
            self.last_inference_ms = 0.0
            return [], 0.0

        orig_h, orig_w = frame.shape[:2]
        inf_w, inf_h = self.inference_size

        t_start = time.perf_counter()

        # Resize frame for faster inference on Raspberry Pi if configured smaller than input
        if (inf_w > 0 and inf_h > 0) and (inf_w != orig_w or inf_h != orig_h):
            resized_frame = cv2.resize(
                frame, (inf_w, inf_h), interpolation=cv2.INTER_LINEAR
            )
            scale_x = orig_w / float(inf_w)
            scale_y = orig_h / float(inf_h)
        else:
            resized_frame = frame
            scale_x = 1.0
            scale_y = 1.0

        min_conf = (
            self.low_conf_threshold
            if return_low_conf_for_bytetrack
            else self.conf_threshold
        )

        detections: List[RawDetection] = []
        try:
            results = self._model.predict(
                source=resized_frame,
                classes=[self.PERSON_CLASS_ID],
                conf=min_conf,
                iou=self.iou_threshold,
                imgsz=max(inf_w, inf_h),
                verbose=False,
            )

            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy_arr = boxes.xyxy.cpu().numpy()
                    confs = boxes.conf.cpu().numpy()
                    cls_ids = (
                        boxes.cls.int().cpu().numpy()
                        if boxes.cls is not None
                        else np.zeros(len(xyxy_arr), dtype=int)
                    )

                    for idx, box in enumerate(xyxy_arr):
                        cls_id = int(cls_ids[idx])
                        if cls_id != self.PERSON_CLASS_ID:
                            continue

                        x1 = max(0, min(orig_w - 1, int(round(box[0] * scale_x))))
                        y1 = max(0, min(orig_h - 1, int(round(box[1] * scale_y))))
                        x2 = max(0, min(orig_w - 1, int(round(box[2] * scale_x))))
                        y2 = max(0, min(orig_h - 1, int(round(box[3] * scale_y))))

                        if x2 <= x1 or y2 <= y1:
                            continue

                        detections.append(
                            RawDetection(
                                bbox=(x1, y1, x2, y2),
                                confidence=round(float(confs[idx]), 4),
                                class_id=self.PERSON_CLASS_ID,
                            )
                        )
        except Exception as exc:
            logger.warning("PersonDetector inference error: %s", exc)

        self.last_inference_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        return detections, self.last_inference_ms

    def export_to_onnx(self, imgsz: Tuple[int, int] = (640, 384)) -> Optional[str]:
        """
        Export the loaded PyTorch YOLO model to ONNX format for lightweight deployment
        on Raspberry Pi 4/5 CPU.
        """
        if not self.is_ready or self._model is None:
            logger.error("Cannot export to ONNX: YOLO model is not loaded.")
            return None
        try:
            exported_path = self._model.export(
                format="onnx",
                imgsz=list(imgsz),
                simplify=True,
                dynamic=False,
            )
            logger.info("Successfully exported YOLO model to ONNX: %s", exported_path)
            return str(exported_path)
        except Exception as exc:
            logger.error("ONNX export failed: %s", exc)
            return None
