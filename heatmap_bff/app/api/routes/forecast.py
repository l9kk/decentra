from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import List

from ...core.config import get_settings
from ...repositories.aggregates_repo import aggregates_repo
from ...services.forecast import generate_forecast, forecast_geojson

router = APIRouter(prefix="/heatmap/forecast", tags=["forecast"])


@router.get("/meta")
async def forecast_meta(
    res: int = Query(..., description="H3 resolution"),
    horizons: str = Query("5,10,15", description="Comma separated horizons in minutes"),
):
    settings = get_settings()
    if res not in aggregates_repo.resolutions():
        raise HTTPException(status_code=400, detail="Unsupported resolution")
    try:
        horizon_list = [int(h.strip()) for h in horizons.split(",") if h.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid horizons format")
    if not horizon_list:
        raise HTTPException(status_code=400, detail="No horizons provided")
    payload = generate_forecast(res, horizon_list)
    return {
        "generated_at": payload["generated_at"],
        "res": res,
        "horizons_minutes": payload["horizons_minutes"],
        "forecast_version": payload["forecast_version"],
        "cells_count": len(payload["cells"]),
        "k_anon_default": settings.suppress_k,
        # heuristic_v2 specific metadata
        "decay_base": payload.get("decay_base"),
        "quantiles": payload.get("quantiles"),
        "alpha_smoothing": payload.get("alpha_smoothing"),
        "corridor_boost": payload.get("corridor_boost"),
        "explanations": payload.get("explanations"),
    }


@router.get("/cells")
async def forecast_cells(
    res: int = Query(...),
    horizons: str = Query("5,10,15"),
    format: str = Query("json", pattern="^(json|geojson)$"),
    polygon: bool = Query(
        True, description="GeoJSON polygons vs points when format=geojson"
    ),
    limit: int | None = Query(None, ge=1, le=50000),
    include_suppressed: bool = Query(False),
    include_enrichment: bool = Query(
        True, description="Include is_hub,is_corridor,decay fields"
    ),
):
    try:
        horizon_list = [int(h.strip()) for h in horizons.split(",") if h.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid horizons format")
    if not horizon_list:
        raise HTTPException(status_code=400, detail="No horizons provided")
    if res not in aggregates_repo.resolutions():
        raise HTTPException(status_code=400, detail="Unsupported resolution")
    try:
        payload = generate_forecast(res, horizon_list)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cells = payload["cells"]
    if not include_suppressed:
        cells = [c for c in cells if not c["suppressed"]]
    if limit:
        cells = cells[:limit]

    # Optionally strip enrichment fields for leaner payload
    if not include_enrichment:
        trimmed = []
        for c in cells:
            c2 = {
                k: v
                for k, v in c.items()
                if k not in ("is_hub", "is_corridor", "decay")
            }
            trimmed.append(c2)
        cells_to_emit = trimmed
    else:
        cells_to_emit = cells
    ret = {**payload, "cells": cells_to_emit}
    if format == "geojson":
        return forecast_geojson(ret, polygon=polygon)
    return ret
