"""
Video Source Routes (`source_routes.py`):
- GET  /sources/current        Active input (camera, uploaded video or browser webcam)
- POST /sources/select         Switch the active input
- POST /sources/video          Upload a video as raw bytes (`?filename=`) and play it
- POST /sources/browser/frame  Push one JPEG frame from the browser webcam
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from starlette.requests import ClientDisconnect

from app.core.auth import require_operator_or_admin
from app.core.config import settings
from app.services.video_source import VideoSourceError, VideoSourceManager

MAX_BROWSER_FRAME_BYTES = 5 * 1024 * 1024

router = APIRouter(prefix="/sources", tags=["Video Sources"])


class SourceSelectRequest(BaseModel):
    mode: Literal["default", "video", "browser"]


def _get_sources(request: Request) -> VideoSourceManager:
    return request.app.state.pipeline_engine.video_sources


def _raise_http(exc: VideoSourceError) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _declared_length(request: Request) -> int:
    try:
        return int(request.headers.get("content-length", "0"))
    except ValueError:
        return 0


@router.get("/current")
async def get_current_source(request: Request) -> Dict[str, Any]:
    status = _get_sources(request).status()
    status["max_upload_mb"] = settings.VIDEO_UPLOAD_MAX_MB
    return status


@router.post("/select", dependencies=[Depends(require_operator_or_admin)])
async def select_source(
    request: Request, payload: SourceSelectRequest
) -> Dict[str, Any]:
    try:
        return _get_sources(request).select(payload.mode)
    except VideoSourceError as exc:
        _raise_http(exc)


@router.post("/video", dependencies=[Depends(require_operator_or_admin)])
async def upload_video(
    request: Request,
    filename: str = Query(..., min_length=1, max_length=255),
) -> Dict[str, Any]:
    """The body is streamed straight to disk, so large videos stay out of memory."""
    sources = _get_sources(request)
    max_bytes = settings.VIDEO_UPLOAD_MAX_MB * 1024 * 1024
    too_large = HTTPException(
        status_code=413,
        detail=f"The video exceeds the {settings.VIDEO_UPLOAD_MAX_MB} MB upload limit.",
    )
    if _declared_length(request) > max_bytes:
        raise too_large

    try:
        path = sources.new_upload_path(filename)
    except VideoSourceError as exc:
        _raise_http(exc)

    written = 0
    try:
        with open(path, "wb") as target:
            async for chunk in request.stream():
                written += len(chunk)
                if written > max_bytes:
                    raise too_large
                await asyncio.to_thread(target.write, chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    except (HTTPException, ClientDisconnect):
        path.unlink(missing_ok=True)
        raise

    try:
        status = await asyncio.to_thread(sources.activate_upload, path, filename)
    except VideoSourceError as exc:
        _raise_http(exc)
    status["max_upload_mb"] = settings.VIDEO_UPLOAD_MAX_MB
    return status


@router.post(
    "/browser/frame",
    status_code=204,
    dependencies=[Depends(require_operator_or_admin)],
)
async def push_browser_frame(request: Request) -> Response:
    if _declared_length(request) > MAX_BROWSER_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="The frame is too large.")
    body = await request.body()
    if len(body) > MAX_BROWSER_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="The frame is too large.")
    try:
        await asyncio.to_thread(_get_sources(request).push_browser_frame, body)
    except VideoSourceError as exc:
        _raise_http(exc)
    return Response(status_code=204)
