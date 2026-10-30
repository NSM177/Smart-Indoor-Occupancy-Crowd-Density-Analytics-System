"""Custom domain exceptions and global FastAPI exception handlers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("backend.exceptions")


class DomainError(Exception):
    """Base exception for domain/business logic violations."""

    def __init__(
        self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class EntityNotFoundError(DomainError):
    def __init__(self, entity: str, identifier: Any) -> None:
        super().__init__(
            f"{entity} with identifier '{identifier}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(
        request: Request, exc: DomainError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "statusCode": exc.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "message": exc.message,
                "detail": exc.message,
            },
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "statusCode": exc.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "message": exc.detail,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg')}"
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "statusCode": 422,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": str(request.url.path),
                "message": errors,
                "detail": errors,
            },
        )
