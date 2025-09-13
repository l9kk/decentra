from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from ...repositories import optional_artifacts
from ...repositories.aggregates_repo import aggregates_repo
import pandas as pd

router = APIRouter(prefix="/intel", tags=["intelligence"])


def _visible_cells_set() -> set[str]:
    cells: set[str] = set()
    for r in aggregates_repo.resolutions():
        df = aggregates_repo.get_resolution(r).df
        cells.update(df["h3"].astype(str).tolist())
    return cells


@router.get("/corridors/top")
async def corridors_top(limit: int = Query(25, ge=1, le=200)):
    df = optional_artifacts.get("od_top.csv")
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="od_top not available")
    vis = _visible_cells_set()
    cols = {c.lower(): c for c in df.columns}
    o_col = cols.get("origin_h3") or cols.get("origin") or list(df.columns)[0]
    d_col = cols.get("dest_h3") or cols.get("destination") or list(df.columns)[1]
    t_col = (
        cols.get("trips")
        or cols.get("count")
        or cols.get("flow")
        or list(df.columns)[2]
    )
    work = df[[o_col, d_col, t_col]].rename(
        columns={o_col: "origin", d_col: "dest", t_col: "trips"}
    )
    work = work[
        (work["origin"].astype(str).isin(vis)) & (work["dest"].astype(str).isin(vis))
    ]
    work = work.sort_values("trips", ascending=False).head(limit)
    if work.empty:
        raise HTTPException(status_code=404, detail="No corridors after filtering")
    max_trips = work["trips"].max() or 1
    work["score"] = work["trips"] / max_trips
    return work.to_dict(orient="records")


@router.get("/hubs/candidates")
async def hubs_candidates(limit: int = Query(25, ge=1, le=200)):
    df = optional_artifacts.get("stop_clusters.csv")
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="stop_clusters not available")
    cols = {c.lower(): c for c in df.columns}
    lat_col = cols.get("lat_center") or cols.get("lat")
    lng_col = cols.get("lng_center") or cols.get("lng")
    tc_col = cols.get("trip_count") or cols.get("trips") or None
    if not lat_col or not lng_col:
        raise HTTPException(
            status_code=400, detail="Cluster file missing lat/lng columns"
        )
    work = df.copy()
    if tc_col is None:
        work["trip_count"] = 1
    else:
        work.rename(columns={tc_col: "trip_count"}, inplace=True)
    work = work.sort_values("trip_count", ascending=False).head(limit)
    max_tc = work["trip_count"].max() or 1
    work["hub_score"] = work["trip_count"] / max_tc
    return [
        {
            "lat": float(r[lat_col]),
            "lng": float(r[lng_col]),
            "trip_count": int(r["trip_count"]),
            "hub_score": float(r["hub_score"]),
        }
        for _, r in work.iterrows()
    ]


@router.get("/anomalies/summary")
async def anomalies_summary(limit: int = Query(20, ge=1, le=200)):
    df = optional_artifacts.get("anomaly_metrics.csv")
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="anomaly_metrics not available")
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    score_col = None
    for candidate in ["score", "anomaly_score", "roughness", "jump_score"]:
        if candidate in df.columns:
            score_col = candidate
            break
    if score_col is None and numeric_cols:
        score_col = numeric_cols[0]
    summary = {"rows": int(len(df)), "score_field": score_col}
    if score_col:
        summary["mean_score"] = float(df[score_col].mean())
        summary["p95_score"] = float(df[score_col].quantile(0.95))
        top = df.sort_values(score_col, ascending=False).head(limit)
        summary["top"] = top.head(limit).to_dict(orient="records")
    return summary


@router.get("/status")
async def intel_status():
    return optional_artifacts.status()
