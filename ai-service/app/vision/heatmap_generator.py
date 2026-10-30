"""
Module 5: Crowd Density Heatmap Generator (`heatmap_generator.py`).
Maintains a temporal Gaussian kernel accumulation matrix with exponential decay,
producing real-time colorized overlays (JET colormap), normalized 2D grids for MQTT/WebSocket,
and saving standalone or blended heatmap images to disk.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from app.schemas.vision_schema import TrackedPerson


class HeatmapGenerator:
    """Accumulates spatial crowd density over time using 2D Gaussian kernels."""

    def __init__(
        self,
        grid_width: int = 64,
        grid_height: int = 36,
        decay_factor: float = 0.96,
    ) -> None:
        self.grid_width = max(16, grid_width)
        self.grid_height = max(12, grid_height)
        self.decay_factor = min(0.999, max(0.80, decay_factor))

        self._lock = threading.RLock()
        self._accumulator = np.zeros(
            (self.grid_height, self.grid_width), dtype=np.float32
        )

        # Precompute 2D Gaussian kernel (radius = 4 grid cells)
        self._radius = 4
        sigma = 1.8
        ax = np.arange(-self._radius, self._radius + 1, dtype=np.float32)
        xx, yy = np.meshgrid(ax, ax)
        kernel = np.exp(-(xx**2 + yy**2) / (2.0 * sigma**2))
        self._kernel = kernel / np.max(kernel)

    def update(self, tracks: List[TrackedPerson]) -> None:
        """Apply exponential decay and deposit Gaussian energy at each person's foot coordinate."""
        with self._lock:
            self._accumulator *= self.decay_factor

            for person in tracks:
                gx = int(
                    min(
                        self.grid_width - 1,
                        max(0, round(person.footPoint.x * (self.grid_width - 1))),
                    )
                )
                gy = int(
                    min(
                        self.grid_height - 1,
                        max(0, round(person.footPoint.y * (self.grid_height - 1))),
                    )
                )
                self._stamp_gaussian(gx, gy, weight=0.35)

            np.clip(self._accumulator, 0.0, 10.0, out=self._accumulator)

    def _stamp_gaussian(self, cx: int, cy: int, weight: float = 0.35) -> None:
        r = self._radius
        x1 = max(0, cx - r)
        x2 = min(self.grid_width, cx + r + 1)
        y1 = max(0, cy - r)
        y2 = min(self.grid_height, cy + r + 1)

        kx1 = r - (cx - x1)
        kx2 = r + (x2 - cx)
        ky1 = r - (cy - y1)
        ky2 = r + (y2 - cy)

        self._accumulator[y1:y2, x1:x2] += (
            self._kernel[ky1:ky2, kx1:kx2] * weight
        )

    def reset(self) -> None:
        with self._lock:
            self._accumulator.fill(0.0)

    def get_normalized_grid(self) -> List[List[float]]:
        """Return a 2D list of values normalized in [0.0, 1.0] for JSON telemetry."""
        with self._lock:
            max_val = float(np.max(self._accumulator))
            if max_val <= 1e-4:
                norm = np.zeros_like(self._accumulator)
            else:
                norm = np.clip(
                    self._accumulator / max(2.5, max_val), 0.0, 1.0
                )
            return np.round(norm, 3).tolist()

    def render_Overlay(
        self, frame: np.ndarray, alpha: float = 0.45
    ) -> np.ndarray:
        """Blend the colorized Gaussian density heatmap onto a BGR video frame."""
        height, width = frame.shape[:2]
        with self._lock:
            acc_copy = self._accumulator.copy()

        max_val = float(np.max(acc_copy))
        if max_val <= 1e-3:
            return frame

        norm = np.clip(acc_copy / max(2.0, max_val), 0.0, 1.0)
        upscaled = cv2.resize(
            norm, (width, height), interpolation=cv2.INTER_CUBIC
        )
        upscaled_u8 = np.uint8(np.clip(upscaled * 255.0, 0, 255))
        colored_heatmap = cv2.applyColorMap(upscaled_u8, cv2.COLORMAP_JET)

        mask = upscaled > 0.05
        output = frame.copy()
        if np.any(mask):
            blended = cv2.addWeighted(
                frame, 1.0 - alpha, colored_heatmap, alpha, 0
            )
            output[mask] = blended[mask]
        return output

    def render_standalone_png(
        self, width: int = 960, height: int = 540
    ) -> bytes:
        """Render a standalone heatmap PNG snapshot as bytes."""
        with self._lock:
            acc_copy = self._accumulator.copy()

        max_val = float(np.max(acc_copy))
        norm = (
            np.clip(acc_copy / max(2.0, max_val), 0.0, 1.0)
            if max_val > 1e-3
            else np.zeros_like(acc_copy)
        )
        upscaled = cv2.resize(
            norm, (width, height), interpolation=cv2.INTER_CUBIC
        )
        upscaled_u8 = np.uint8(np.clip(upscaled * 255.0, 0, 255))
        colored = cv2.applyColorMap(upscaled_u8, cv2.COLORMAP_JET)
        ok, buf = cv2.imencode(".png", colored)
        return buf.tobytes() if ok else b""

    def save_image(
        self,
        save_dir_or_file: str | Path,
        background_frame: Optional[np.ndarray] = None,
        width: int = 1280,
        height: int = 720,
    ) -> str:
        """
        Save the current Density Heatmap to disk as a PNG file.
        If `background_frame` is provided, saves the blended overlay; otherwise saves
        the standalone colorized heatmap.
        Returns the absolute file path written.
        """
        target = Path(save_dir_or_file)
        if target.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            target.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = target / f"density_heatmap_{ts}.png"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)

        if background_frame is not None and background_frame.size > 0:
            img_to_save = self.render_Overlay(background_frame, alpha=0.50)
        else:
            png_bytes = self.render_standalone_png(width=width, height=height)
            arr = np.frombuffer(png_bytes, dtype=np.uint8)
            img_to_save = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        cv2.imwrite(str(target), img_to_save)
        return str(target.resolve())
