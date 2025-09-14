from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
import pandas as pd

from ...core.config import get_settings
from ...models.schemas import CellOut, MetaOut, ErrorOut, MetaResolution, Center
from ...repositories.aggregates_repo import aggregates_repo
from ...utils.geo import parse_bbox_query, point_in_bbox
from ..deps import validate_resolution
from hashlib import sha1
from datetime import datetime
import h3

router = APIRouter(prefix="/heatmap", tags=["heatmap"])


@router.get("/meta", response_model=MetaOut)
async def meta() -> MetaOut:
    settings = get_settings()
    resolutions: list[MetaResolution] = []
    for r in aggregates_repo.resolutions():
        agg = aggregates_repo.get_resolution(r)
        df = agg.df
        suppressed_mask = (df["point_count"] < settings.suppress_k) | (
            df["unique_trips"] < settings.suppress_k
        )
        cells_after = int((~suppressed_mask).sum())
        resolutions.append(
            MetaResolution(
                res=r,
                cells_before=int(len(df)),
                cells_after_suppression=cells_after,
                total_points=agg.total_points,
                total_trips=agg.total_trips,
            )
        )
    return MetaOut(
        resolutions=resolutions,
        k_anon_default=settings.suppress_k,
        center=Center(lat=settings.city_center_lat, lng=settings.city_center_lng),
        bbox=settings.astana_bbox,
        last_loaded_at=aggregates_repo.loaded_at or datetime.utcnow(),
    )


@router.get("/top", response_model=list[CellOut])
async def top(
    res: int | None = Query(None),
    metric: str = Query("points", pattern="^(points|trips)$"),
    limit: int = Query(50, ge=1, le=1000),
):
    settings = get_settings()
    res_final = (
        res
        if (res is not None and res in aggregates_repo.resolutions())
        else settings.default_h3_res
    )
    agg = aggregates_repo.get_resolution(res_final)
    df = agg.df.copy()

    # Choose sorting column: prefer score if available, otherwise use metric
    if "score" in df.columns:
        sort_col = "score"
        ascending = False
    else:
        sort_col = "point_count" if metric == "points" else "unique_trips"
        ascending = False

    df = df.sort_values(sort_col, ascending=ascending).head(limit)
    total_points = agg.total_points or 1
    total_trips = agg.total_trips or 1
    out: list[CellOut] = []
    metric_col = "point_count" if metric == "points" else "unique_trips"
    for _, r in df.iterrows():
        out.append(
            CellOut(
                h3=r["h3"],
                res=int(r["res"]),
                point_count=int(r["point_count"]),
                unique_trips=int(r["unique_trips"]),
                value=int(r[metric_col]),
                share_points=float(r["point_count"] / total_points),
                share_trips=float(r["unique_trips"] / total_trips),
                center=Center(lat=float(r["lat_center"]), lng=float(r["lng_center"])),
                suppressed=False,
                schema_version="1.0.0",
                score=(
                    float(r["score"])
                    if "score" in r and not pd.isna(r["score"])
                    else None
                ),
                score_quantile=(
                    float(r["score_quantile"])
                    if "score_quantile" in r
                    and not pd.isna(r["score_quantile"])
                    else None
                ),
            )
        )
    return [c.model_dump() for c in out]


@router.get(
    "/cells",
    response_model=list[CellOut],
    responses={200: {"model": list[CellOut]}, 400: {"model": ErrorOut}},
)
async def cells(
    response: Response,
    res: int = Depends(validate_resolution),
    metric: str = Query("points", pattern="^(points|trips)$"),
    include_suppressed: bool = Query(False),
    k: int | None = Query(None, ge=1),
    bbox: str | None = Query(None, description="minLat,minLng,maxLat,maxLng"),
    format: str = Query("json", pattern="^(json|geojson)$"),
    polygon: bool = Query(
        True,
        description="When geojson, if true return Polygon cells else Point centers",
    ),
    limit: int | None = Query(None, ge=1, le=50000),
):
    settings = get_settings()
    agg = aggregates_repo.get_resolution(res)
    df = agg.df.copy()
    bbox_obj = parse_bbox_query(bbox)
    if bbox_obj:
        df = df[
            df.apply(
                lambda r: point_in_bbox(r["lat_center"], r["lng_center"], bbox_obj),
                axis=1,
            )
        ]
    if df.empty:
        raise HTTPException(status_code=400, detail="No cells in selection")
    total_points = agg.total_points or 1
    total_trips = agg.total_trips or 1
    df["share_points"] = df["point_count"] / total_points
    df["share_trips"] = df["unique_trips"] / total_trips
    k_val = k or settings.suppress_k
    suppressed_mask = (df["point_count"] < k_val) | (df["unique_trips"] < k_val)
    value_col = "point_count" if metric == "points" else "unique_trips"
    df["value"] = df[value_col]
    if not include_suppressed:
        df = df[~suppressed_mask]
    else:
        df.loc[suppressed_mask, "value"] = None
    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="No cells after suppression; try lowering k or include_suppressed=true",
        )
    df = df.sort_values(value_col, ascending=False)
    if limit:
        df = df.head(limit)
    cells_out: list[CellOut] = []
    max_val = df[value_col].max() or 1
    for _, r in df.iterrows():
        cells_out.append(
            CellOut(
                h3=r["h3"],
                res=int(r["res"]),
                point_count=int(r["point_count"]),
                unique_trips=int(r["unique_trips"]),
                value=(None if r["value"] is None else int(r["value"])),
                share_points=float(r["share_points"]),
                share_trips=float(r["share_trips"]),
                center=Center(lat=float(r["lat_center"]), lng=float(r["lng_center"])),
                suppressed=bool(
                    (r["point_count"] < k_val) or (r["unique_trips"] < k_val)
                ),
                schema_version="1.0.0",
                score=(
                    float(r["score"])
                    if "score" in r and not pd.isna(r["score"])
                    else None
                ),
                score_quantile=(
                    float(r["score_quantile"])
                    if "score_quantile" in r
                    and not pd.isna(r["score_quantile"])
                    else None
                ),
            )
        )
    base = f"{res}|{metric}|{k_val}|{bbox}|{len(cells_out)}|{aggregates_repo.loaded_at}"
    etag = 'W/"' + sha1(base.encode()).hexdigest() + '"'
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60"
    if format == "geojson":
        features = []
        for c in cells_out:
            props = c.model_dump(exclude={"center"})
            # demand_index for live layer
            if c.value is not None:
                props["demand_index"] = round(
                    (c.value / max_val) if max_val else 0.0, 4
                )
            if polygon:
                boundary = h3.cell_to_boundary(c.h3, geo_json=True)
                geometry = {"type": "Polygon", "coordinates": [boundary]}
            else:
                geometry = {
                    "type": "Point",
                    "coordinates": [c.center.lng, c.center.lat],
                }
            features.append(
                {"type": "Feature", "geometry": geometry, "properties": props}
            )
        return {"type": "FeatureCollection", "features": features}
    return [c.model_dump() for c in cells_out]
