"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .api.routes import router
from .config import get_settings
from .errors import register_error_handlers
from .security import SlidingWindowRateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cloudops.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db.init_db()
    logger.info(
        "CloudOps AI Agent starting: demo_mode=%s gcp=%s aws=%s llm=%s",
        settings.demo_mode, settings.gcp_enabled, settings.aws_enabled, settings.llm_provider,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "AI-powered cloud operations incident investigation. "
            "Read-only cloud access; demo mode serves clearly-labeled simulated data."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    general_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
    investigate_limiter = SlidingWindowRateLimiter(settings.investigations_rate_limit_per_minute)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        client = request.client.host if request.client else "unknown"
        if request.method == "POST" and request.url.path.endswith("/investigations"):
            if not investigate_limiter.allow(f"inv:{client}"):
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "rate_limited",
                                       "message": "Too many investigations started; retry in a minute."}},
                )
        if not general_limiter.allow(client):
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Rate limit exceeded. Retry later."}},
            )
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
