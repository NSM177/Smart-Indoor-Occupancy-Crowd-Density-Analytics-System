"""
REST & Streaming Routes for the AI Vision Service (`routes.py`):
- GET  /health
- GET  /analytics/current
- GET  /analytics/zones
- GET  /telemetry/latest
- POST /heatmap/save
- POST /heatmap/reset
- POST /config/reload
- GET  /streams/{camera_id}/mjpeg
- GET  /streams/{camera_id}/heatmap-snapshot
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.services.pipeline_engine import VisionPipelineEngine

router = APIRouter()


def _get_engine(request: Request) -> VisionPipelineEngine:
    return request.app.state.pipeline_engine


@router.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """Return AI engine health, FPS, inference_ms, processing_ms, and MQTT/Camera status."""
    engine = _get_engine(request)
    return engine.get_status()


@router.get("/analytics/current")
async def get_current_analytics(request: Request) -> Dict[str, Any]:
    """
    Unified JSON endpoint returning real-time occupancy count, virtual line IN/OUT counts,
    tracked individuals, zone density summary, active hysteresis alerts, and performance stats.
    Provides both camelCase and snake_case keys for seamless cross-service compatibility.
    """
    engine = _get_engine(request)
    payload = engine._latest_telemetry_payload
    if payload is None:
        perf = engine.profiler.get_metrics(
            engine.detector.backend_name
        ).model_dump()
        perf["inference_ms"] = perf.get("inferenceTimeMs", 0.0)
        perf["processing_ms"] = perf.get("processingTimeMs", 0.0)
        return {
            "status": "warming_up",
            "roomId": engine.config.roomId,
            "room_id": engine.config.roomId,
            "roomName": engine.config.roomName,
            "totalCount": 0,
            "current_count": 0,
            "in_count": 0,
            "out_count": 0,
            "roomDensity": 0.0,
            "overall_density": 0.0,
            "roomOccupancyRate": 0.0,
            "capacity_ratio": 0.0,
            "roomDensityLevel": "LOW",
            "alert_level": "NORMAL",
            "lineCounts": [],
            "tracks": [],
            "zones": [],
            "activeAlerts": [],
            "heatmapGrid": engine.heatmap.get_normalized_grid(),
            "heatmap_grid": engine.heatmap.get_normalized_grid(),
            "performance": perf,
        }

    data = payload.model_dump()
    perf = data.get("performance", {})
    perf["inference_ms"] = perf.get("inferenceTimeMs", 0.0)
    perf["processing_ms"] = perf.get("processingTimeMs", 0.0)
    data["performance"] = perf

    in_cnt = sum(int(lc.get("inCount", 0)) for lc in data.get("lineCounts", []))
    out_cnt = sum(int(lc.get("outCount", 0)) for lc in data.get("lineCounts", []))
    lvl = str(data.get("roomDensityLevel", "LOW")).upper()
    alert_lvl = "CRITICAL" if lvl == "CRITICAL" else ("WARNING" if lvl == "HIGH" else "NORMAL")

    data.update(
        {
            "room_id": data.get("roomId"),
            "current_count": data.get("totalCount", 0),
            "in_count": in_cnt,
            "out_count": out_cnt,
            "overall_density": data.get("roomDensity", 0.0),
            "capacity_ratio": round(float(data.get("roomOccupancyRate", 0.0)) / 100.0, 4),
            "alert_level": alert_lvl,
            "heatmap_grid": data.get("heatmapGrid", []),
        }
    )
    return data


@router.get("/analytics/zones")
async def get_zones_analytics(request: Request) -> Dict[str, Any]:
    """
    Return detailed zone-by-zone occupancy count, calibrated density (people/m²),
    occupancy rate (%), average dwell time, and active alert status.
    """
    engine = _get_engine(request)
    payload = engine._latest_telemetry_payload
    zones_data = (
        [z.model_dump() for z in payload.zones]
        if payload is not None
        else [
            {
                "zoneId": z.id,
                "zoneCode": z.code,
                "zoneName": z.name,
                "areaSqm": z.areaSqm,
                "maxCapacity": z.maxCapacity,
                "count": 0,
                "density": 0.0,
                "occupancyRate": 0.0,
                "densityLevel": "LOW",
                "warningDensityThreshold": z.warningDensityThreshold,
                "criticalDensityThreshold": z.criticalDensityThreshold,
                "avgDwellTimeSec": 0.0,
                "alertActive": False,
            }
            for z in engine.config.zones
            if z.isActive
        ]
    )
    return {
        "timestamp": payload.timestamp if payload else None,
        "roomId": engine.config.roomId,
        "roomName": engine.config.roomName,
        "totalZones": len(zones_data),
        "zones": zones_data,
    }


@router.get("/telemetry/latest")
async def latest_telemetry(request: Request) -> Dict[str, Any]:
    return await get_current_analytics(request)


@router.post("/config/reload")
async def reload_config(
    request: Request, payload: Dict[str, Any]
) -> Dict[str, Any]:
    engine = _get_engine(request)
    updated = engine.apply_config_dict(payload)
    return {
        "reloaded": True,
        "roomId": updated.roomId,
        "zonesCount": len(updated.zones),
        "virtualLinesCount": len(updated.virtualLines),
    }


@router.post("/heatmap/save")
async def save_heatmap_to_disk(
    request: Request,
    filepath: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Save the current spatial density heatmap image to disk and return its path."""
    engine = _get_engine(request)
    saved_path = engine.save_current_heatmap(custom_path=filepath)
    return {"saved": True, "filePath": saved_path}


@router.post("/heatmap/reset")
async def reset_heatmap(request: Request) -> Dict[str, Any]:
    engine = _get_engine(request)
    engine.heatmap.reset()
    return {"reset": True}


@router.get("/streams/{camera_id}/heatmap-snapshot")
async def get_heatmap_snapshot(
    request: Request,
    camera_id: str,
) -> Response:
    engine = _get_engine(request)
    png_bytes = engine.heatmap.render_standalone_png(width=960, height=540)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/stream.mjpg")
@router.get("/streams/{camera_id}/mjpeg")
async def stream_mjpeg(
    request: Request,
    camera_id: str = "default",
    overlay_zones: bool = Query(default=True),
    overlay_heatmap: bool = Query(default=False),
) -> StreamingResponse:
    engine = _get_engine(request)

    async def frame_generator() -> AsyncGenerator[bytes, None]:
        while True:
            if await request.is_disconnected():
                break
            jpeg_bytes = engine.get_annotated_jpeg(
                overlay_zones=overlay_zones,
                overlay_heatmap=overlay_heatmap,
            )
            if jpeg_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(jpeg_bytes)).encode("ascii")
                    + b"\r\n\r\n"
                    + jpeg_bytes
                    + b"\r\n"
                )
            await asyncio.sleep(0.066)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
