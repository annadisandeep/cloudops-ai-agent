"""Consistent API error envelope and handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("cloudops.errors")


class ApiError(Exception):
    """Application error carried to the client in a safe envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__("not_found", message, 404)


class ValidationApiError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__("validation_error", message, 400)


class ProviderDisabledError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__("provider_disabled", message, 403)


class RateLimitedError(ApiError):
    def __init__(self, message: str = "Rate limit exceeded. Retry later.") -> None:
        super().__init__("rate_limited", message, 429)


def _envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Summarize without echoing arbitrary submitted values back.
        parts = []
        for err in exc.errors()[:5]:
            loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
            parts.append(f"{loc}: {err.get('msg', 'invalid')}")
        return JSONResponse(
            status_code=422,
            content=_envelope("request_invalid", "; ".join(parts) or "Invalid request"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=_envelope("internal_error", "An internal error occurred.")
        )
