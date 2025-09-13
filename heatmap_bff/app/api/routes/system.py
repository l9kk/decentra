from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from ...core.config import get_settings
from ...repositories.loader import load_or_precomputed
from ...repositories.aggregates_repo import aggregates_repo
from ...repositories import optional_artifacts
from ...models.schemas import HealthOut, Center

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@router.get("/version")
async def version():
    settings = get_settings()
    return {
        "app": "Mobility Heatmap BFF",
        "version": "0.1.0",
        "schema_version": settings.schema_version,
    }


@router.post("/admin/reload")
async def admin_reload():  # hackathon only (no auth)
    try:
        load_or_precomputed()
        optional_artifacts.reload()
        return {"status": "reloaded", "resolutions": aggregates_repo.resolutions()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Reload failed: {e}") from e


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    settings = get_settings()
    return HealthOut(
        resolutions=aggregates_repo.resolutions(),
        k_anon=settings.suppress_k,
        total_points=aggregates_repo.totals_points(),
        total_trips=aggregates_repo.totals_trips(),
        center=Center(lat=settings.city_center_lat, lng=settings.city_center_lng),
    )
