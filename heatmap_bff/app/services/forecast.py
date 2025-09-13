from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Set
from datetime import datetime
import math
import statistics

import pandas as pd
import h3

from ..core.config import get_settings
from ..repositories.aggregates_repo import aggregates_repo


@dataclass
class ForecastCell:
    h3: str
    current_count: int
    unique_trips: int
    suppressed: bool
    predictions: Dict[
        int, Dict[str, float]
    ]  # horizon -> {predicted, lower, upper, demand_index}


_forecast_cache: Dict[str, Dict[str, object]] = {}

# Lazy loaded enrichment sets per resolution
_hub_cells_cache: Dict[int, Set[str]] = {}
_corridor_cells_cache: Dict[int, Set[str]] = {}


def _load_hubs(res: int) -> Set[str]:
    if res in _hub_cells_cache:
        return _hub_cells_cache[res]
    settings = get_settings()
    hubs: Set[str] = set()
    try:
        df = pd.read_csv(f"{settings.artifacts_dir}/stop_clusters.csv")
        # take top N hubs by count (hard cap 50 for performance)
        df = df.sort_values("count", ascending=False).head(50)
        for _, r in df.iterrows():
            try:
                hubs.add(
                    h3.latlng_to_cell(float(r["lat_mean"]), float(r["lng_mean"]), res)
                )
            except Exception:  # pragma: no cover - robustness
                continue
    except Exception:
        pass
    _hub_cells_cache[res] = hubs
    return hubs


def _load_corridor_cells(res: int) -> Set[str]:
    if res in _corridor_cells_cache:
        return _corridor_cells_cache[res]
    settings = get_settings()
    cells: Set[str] = set()
    try:
        # Only parse limited rows to avoid huge geometry column cost
        df = pd.read_csv(
            f"{settings.artifacts_dir}/od_top.csv",
            usecols=["start_cluster", "end_cluster", "trip_count"],
            nrows=200,
        )
        # treat clusters with high trip_count as corridor anchors
        df = df.sort_values("trip_count", ascending=False).head(100)
        # We do not have cluster centroid file here; fallback: reuse stop_clusters centroids subset mapping by id if available
        sc_path = f"{settings.artifacts_dir}/stop_clusters.csv"
        if pd.io.common.is_file_like(sc_path) or True:
            try:
                sc = pd.read_csv(sc_path)
                cluster_map = {
                    int(r["cluster_id"]): (float(r["lat_mean"]), float(r["lng_mean"]))
                    for _, r in sc.iterrows()
                }
                for _, r in df.iterrows():
                    for cid_col in ("start_cluster", "end_cluster"):
                        cid = int(r[cid_col])
                        if cid in cluster_map:
                            lat, lng = cluster_map[cid]
                            try:
                                cells.add(h3.latlng_to_cell(lat, lng, res))
                            except Exception:
                                continue
            except Exception:
                pass
    except Exception:
        pass
    _corridor_cells_cache[res] = cells
    return cells


def _cache_key(res: int, horizons: Sequence[int]) -> str:
    settings = get_settings()
    minute_bucket = datetime.utcnow().strftime("%Y%m%d%H%M")  # minute granularity
    return f"{res}|{','.join(map(str, sorted(horizons)))}|{minute_bucket}|{aggregates_repo.loaded_at}|{settings.forecast_decay_per_hour}"


def _poisson_ci(mean: float) -> tuple[float, float]:
    # Normal approximation (mean large enough in aggregated heatmap use case)
    if mean <= 0:
        return 0.0, 0.0
    sd = math.sqrt(mean)
    return max(0.0, mean - 1.96 * sd), mean + 1.96 * sd


def generate_forecast(res: int, horizons: Sequence[int]) -> dict:
    """Heuristic forecast generation with variable decay, neighbor smoothing and enrichment.

    Steps:
      1. Load aggregates for resolution.
      2. Compute density tiers & assign per-cell decay.
      3. Neighbor smoothing on current count (k-ring 1) with alpha blending.
      4. Corridor & hub adjustments (slower decay near hubs, short-horizon boost in corridors).
      5. Predict counts per horizon and build demand indices using blended denominator (0.5*max + 0.5*p95).
    """
    settings = get_settings()
    horizons = sorted(set(int(h) for h in horizons))
    for h in horizons:
        if h < 1 or h > settings.forecast_max_minutes:
            raise ValueError(f"Invalid horizon {h}")
    key = _cache_key(res, horizons)
    cached = _forecast_cache.get(key)
    if cached:
        return cached  # type: ignore[return-value]

    agg = aggregates_repo.get_resolution(res)
    df = agg.df.copy()
    if df.empty:
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "res": res,
            "horizons_minutes": horizons,
            "forecast_version": "heuristic_v2",
            "cells": [],
        }

    k = settings.suppress_k
    suppressed_mask = (df["point_count"] < k) | (df["unique_trips"] < k)

    # Density tiers
    counts = df["point_count"].tolist()
    q50 = statistics.quantiles(counts, n=100)[49] if len(counts) > 1 else 0
    q80 = statistics.quantiles(counts, n=100)[79] if len(counts) > 1 else q50
    q95 = statistics.quantiles(counts, n=100)[94] if len(counts) > 1 else q80
    base_decay = settings.forecast_decay_per_hour

    hubs = _load_hubs(res)
    corridors = _load_corridor_cells(res)

    # Prebuild neighbor map (k-ring 1)
    cell_set = set(df["h3"].tolist())
    neighbor_map: Dict[str, List[str]] = {}
    for h3cell in cell_set:
        neighbor_map[h3cell] = [
            n for n in h3.k_ring(h3cell, 1) if n in cell_set and n != h3cell
        ]

    alpha = 0.7  # smoothing weight
    corridor_boost = 0.10
    corridor_tau_hours = 0.5

    records: List[ForecastCell] = []

    # Helper to get decay per cell
    def decay_for(pc: int, h3cell: str) -> float:
        if pc >= q95:
            d = base_decay * 0.4
        elif pc >= q80:
            d = base_decay * 0.7
        elif pc >= q50:
            d = base_decay * 1.0
        else:
            d = base_decay * 1.3
        if h3cell in hubs:
            d = min(d, base_decay * 0.5)
        return d

    # First pass: compute smoothed current counts and decay
    enriched: List[Dict[str, object]] = []
    for _, r in df.iterrows():
        cell_id = r["h3"]
        pc = int(r["point_count"])
        neighs = neighbor_map.get(cell_id, [])
        neigh_mean = (
            statistics.mean(
                [int(df.loc[df["h3"] == n, "point_count"].iloc[0]) for n in neighs]
            )
            if neighs
            else pc
        )
        smoothed = alpha * pc + (1 - alpha) * neigh_mean
        enriched.append(
            {
                "h3": cell_id,
                "point_count": pc,
                "smoothed": smoothed,
                "unique_trips": int(r["unique_trips"]),
                "decay": decay_for(pc, cell_id),
                "is_corridor": cell_id in corridors,
                "is_hub": cell_id in hubs,
                "suppressed": bool((pc < k) or (int(r["unique_trips"]) < k)),
            }
        )

    max_pred_by_h: Dict[int, float] = {h: 0.0 for h in horizons}
    preds_per_cell: Dict[str, Dict[int, Dict[str, float]]] = {}

    for row in enriched:
        cell_preds: Dict[int, Dict[str, float]] = {}
        for h in horizons:
            hours = h / 60.0
            lam = row["decay"]  # type: ignore[index]
            base_val = row["smoothed"]  # type: ignore[index]
            predicted = float(base_val) * math.exp(-lam * hours)
            # Corridor short-horizon persistence boost
            if row["is_corridor"] and hours <= 0.5:
                boost = corridor_boost * math.exp(-hours / corridor_tau_hours)
                predicted *= 1 + boost
            lower, upper = _poisson_ci(predicted)
            # Tier-based CI scaling
            pc = row["point_count"]  # type: ignore[index]
            if pc >= q95:
                scale = 0.8
            elif pc < q50:
                scale = 1.3
            else:
                scale = 1.0
            mid = predicted
            half_width = (upper - lower) / 2 * scale
            lower = max(0.0, mid - half_width)
            upper = mid + half_width
            cell_preds[h] = {"predicted": predicted, "lower": lower, "upper": upper}
            if predicted > max_pred_by_h[h]:
                max_pred_by_h[h] = predicted
        preds_per_cell[row["h3"]] = cell_preds  # type: ignore[index]

    # Compute p95 per horizon for blended demand index
    demand_denoms: Dict[int, float] = {}
    for h in horizons:
        vals = [preds_per_cell[c][h]["predicted"] for c in preds_per_cell]
        if vals:
            sorted_vals = sorted(vals)
            p95_idx = max(0, int(0.95 * (len(vals) - 1)))
            p95 = sorted_vals[p95_idx]
            demand_denoms[h] = 0.5 * (max_pred_by_h[h] or 1.0) + 0.5 * (p95 or 1.0)
        else:
            demand_denoms[h] = 1.0

    cells_payload = []
    for row in enriched:
        cell_preds = preds_per_cell[row["h3"]]  # type: ignore[index]
        out_preds: Dict[str, Dict[str, float]] = {}
        for h, d in cell_preds.items():
            denom = demand_denoms[h] or 1.0
            out_preds[str(h)] = {
                "predicted": round(d["predicted"], 3),
                "lower": round(d["lower"], 3),
                "upper": round(d["upper"], 3),
                "demand_index": round(d["predicted"] / denom, 4),
            }
        cells_payload.append(
            {
                "h3": row["h3"],
                "current_count": row["point_count"],
                "unique_trips": row["unique_trips"],
                "suppressed": row["suppressed"],
                "is_hub": row["is_hub"],
                "is_corridor": row["is_corridor"],
                "decay": round(row["decay"], 5),
                "predictions": out_preds,
            }
        )

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "res": res,
        "horizons_minutes": horizons,
        "forecast_version": "heuristic_v2",
        "decay_base": base_decay,
        "quantiles": {"q50": q50, "q80": q80, "q95": q95},
        "alpha_smoothing": alpha,
        "corridor_boost": corridor_boost,
        "cells": cells_payload,
        "explanations": {
            "temporal_basis": "single-snapshot heuristic without historical timestamps",
            "components": [
                "variable_decay_tiers",
                "neighbor_smoothing",
                "corridor_short_horizon_boost",
                "hub_decay_clamp",
                "blended_demand_index",
                "tier_scaled_confidence_intervals",
            ],
        },
    }
    _forecast_cache[key] = payload
    return payload


def forecast_geojson(payload: dict, polygon: bool = True) -> dict:
    features = []
    for cell in payload["cells"]:
        if polygon:
            boundary = h3.cell_to_boundary(cell["h3"], geo_json=True)
            geometry = {"type": "Polygon", "coordinates": [boundary]}
        else:
            # fallback point: compute center from boundary average (h3 lib has cell_to_latlng in v4 python?)
            boundary = h3.cell_to_boundary(cell["h3"], geo_json=True)
            lon = sum(p[0] for p in boundary) / len(boundary)
            lat = sum(p[1] for p in boundary) / len(boundary)
            geometry = {"type": "Point", "coordinates": [lon, lat]}
        properties = {k: v for k, v in cell.items() if k != "h3"}
        properties["h3"] = cell["h3"]
        features.append(
            {"type": "Feature", "geometry": geometry, "properties": properties}
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {k: v for k, v in payload.items() if k != "cells"},
    }
