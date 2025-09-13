from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core.config import get_settings
from .core.logging import configure_logging
from .repositories.loader import load_or_precomputed
from .repositories import optional_artifacts
from .api.routes.heatmap import router as heatmap_router
from .api.routes.future_stubs import router as future_router
from .api.routes.system import router as system_router
from .api.routes.intelligence import router as intel_router

configure_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Mobility Heatmap BFF", version="0.1.0")

    # Middleware
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allow_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(system_router)
    app.include_router(heatmap_router)
    app.include_router(intel_router)
    app.include_router(future_router)

    @app.on_event("startup")
    def _startup() -> None:  # pragma: no cover - startup side effect
        logger.info("Loading aggregates...")
        load_or_precomputed()
        optional_artifacts.preload()
        logger.info("Startup load complete")

    # Generic exception handler (simple JSON)
    @app.exception_handler(Exception)
    async def generic_handler(_, exc: Exception):  # noqa: ANN001
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return app


app = create_app()
