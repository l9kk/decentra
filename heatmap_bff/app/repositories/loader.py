from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, Iterator
import pandas as pd
import numpy as np
import h3

from .aggregates_repo import ResolutionAggregate, aggregates_repo
from ..core.config import get_settings
from ..utils.geo import parse_bbox, point_in_bbox

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = ["randomized_id", "lat", "lng", "alt", "spd", "azm"]


def _validate_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _iter_chunks(path: str, chunksize: int = 200_000) -> Iterator[pd.DataFrame]:
    for chunk in pd.read_csv(path, chunksize=chunksize):
        yield chunk


def load_or_precomputed() -> None:
    settings = get_settings()
    if settings.precomputed_agg:
        path = settings.precomputed_agg
        p = Path(path)
        if not p.exists() and path.startswith("./outputs/"):
            if not p.exists():
                raise FileNotFoundError(
                    f"Precomputed aggregates not found at {p}. Run the build script: python -m heatmap_bff.scripts.build_precomputed --input <raw.csv> --out {path}"
                )
                p = alt
        logger.info("Loading precomputed aggregates from %s", p)
        pre = pd.read_csv(p)
        # Normalize columns from external artifact formats
        column_map = {}
        if "h3_index" in pre.columns and "h3" not in pre.columns:
            column_map["h3_index"] = "h3"
        if "resolution" in pre.columns and "res" not in pre.columns:
            column_map["resolution"] = "res"
        if column_map:
            pre = pre.rename(columns=column_map)
        expected = {"h3", "res", "point_count", "unique_trips"}
        missing = expected.difference(set(pre.columns))
        if missing:
            raise ValueError(f"PRECOMPUTED_AGG missing required columns: {missing}")
        # compute centers (h3 v4: cell_to_latlng)
        pre[["lat_center", "lng_center"]] = (
            pre["h3"].map(h3.cell_to_latlng).apply(pd.Series)
        )
        for res, grp in pre.groupby("res"):
            _register_res(res, grp)
        return

    logger.info("Aggregating raw CSV %s", settings.data_csv)
    bbox = parse_bbox(settings.astana_bbox) if settings.astana_bbox else None

    # Accumulators: {res: {h3: {points:int, ids:set()}}}
    accum: Dict[int, Dict[str, dict]] = {r: {} for r in settings.supported_resolutions}

    for chunk in _iter_chunks(settings.data_csv):
        _validate_columns(chunk)
        # Drop NaNs early
        chunk = chunk.dropna(subset=["randomized_id", "lat", "lng"])  # minimal
        if bbox:
            chunk = chunk[
                chunk.apply(lambda r: point_in_bbox(r["lat"], r["lng"], bbox), axis=1)
            ]
        if chunk.empty:
            continue
        # vectorize lat/lng arrays
        lats = chunk["lat"].to_numpy()
        lngs = chunk["lng"].to_numpy()
        ids = chunk["randomized_id"].astype(str).to_numpy()
        for res in settings.supported_resolutions:
            # h3 v4: latlng_to_cell replaces geo_to_h3
            cells = [
                h3.latlng_to_cell(la, ln, res)
                for la, ln in zip(lats, lngs, strict=False)
            ]
            for h, trip in zip(cells, ids, strict=False):
                bucket = accum[res].setdefault(h, {"points": 0, "ids": set()})
                bucket["points"] += 1
                bucket["ids"].add(trip)

    # Finalize into DataFrames
    for res, mapping in accum.items():
        rows = []
        for cell, data in mapping.items():
            lat_center, lng_center = h3.cell_to_latlng(cell)
            rows.append(
                {
                    "h3": cell,
                    "res": res,
                    "point_count": data["points"],
                    "unique_trips": len(data["ids"]),
                    "lat_center": lat_center,
                    "lng_center": lng_center,
                }
            )
        df_res = pd.DataFrame(rows)
        _register_res(res, df_res)


def _register_res(res: int, df_res: pd.DataFrame) -> None:
    total_points = int(df_res["point_count"].sum())
    total_trips = int(df_res["unique_trips"].sum())
    # Demand scoring (hackathon heuristic):
    # trip_intensity: normalized point_count
    # uniqueness_factor: unique_trips / point_count (clipped)
    # score = 0.6 * trip_intensity + 0.4 * uniqueness_factor
    if not df_res.empty:
        max_points = df_res["point_count"].max() or 1
        df_res["_trip_intensity"] = df_res["point_count"] / max_points
        df_res["_uniqueness_factor"] = (
            df_res["unique_trips"] / df_res["point_count"].clip(lower=1)
        ).clip(0, 1)
        df_res["score"] = (
            0.6 * df_res["_trip_intensity"] + 0.4 * df_res["_uniqueness_factor"]
        )
        # Quantile rank (0..1)
        df_res["score_quantile"] = df_res["score"].rank(pct=True)
        df_res.drop(columns=["_trip_intensity", "_uniqueness_factor"], inplace=True)
    aggregates_repo.set_resolution(
        ResolutionAggregate(
            res=res, df=df_res, total_points=total_points, total_trips=total_trips
        )
    )
