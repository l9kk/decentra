from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
from ..repositories.aggregates_repo import aggregates_repo

logger = logging.getLogger(__name__)


def _highest_res_df() -> pd.DataFrame:
    res_list = sorted(aggregates_repo.resolutions())
    if not res_list:
        return pd.DataFrame()
    return aggregates_repo.get_resolution(res_list[-1]).df.copy()


def build_stop_clusters(out_path: Path, top_cells: int = 500) -> None:
    df = _highest_res_df()
    if df.empty:
        logger.warning("Cannot build stop_clusters: no aggregates yet")
        return
    cols_needed = {"lat_center", "lng_center", "point_count", "unique_trips"}
    if not cols_needed.issubset(df.columns):
        logger.warning("Missing columns for stop cluster build; skipping")
        return
    if "score" not in df.columns:
        # fallback simple score
        max_points = df["point_count"].max() or 1
        df["score"] = df["point_count"] / max_points
    df_top = df.sort_values("score", ascending=False).head(top_cells)
    # simple grid clustering by rounding
    df_top["grid_lat"] = (df_top["lat_center"] * 100).round().astype(int)
    df_top["grid_lng"] = (df_top["lng_center"] * 100).round().astype(int)
    grouped = (
        df_top.groupby(["grid_lat", "grid_lng"], as_index=False)
        .agg(
            lat_center=("lat_center", "mean"),
            lng_center=("lng_center", "mean"),
            point_sum=("point_count", "sum"),
            trip_sum=("unique_trips", "sum"),
            avg_score=("score", "mean"),
            cell_count=("h3", "count"),
        )
        .sort_values("point_sum", ascending=False)
    )
    grouped.rename(
        columns={"point_sum": "trip_count"}, inplace=True
    )  # align with hubs endpoint expectation
    grouped.to_csv(out_path, index=False)
    logger.info(
        "Built stop_clusters artifact at %s (%d clusters)", out_path, len(grouped)
    )


def build_anomaly_metrics(out_path: Path) -> None:
    df = _highest_res_df()
    if df.empty:
        logger.warning("Cannot build anomaly_metrics: no aggregates yet")
        return
    metrics = []
    pc = df["point_count"].astype(float)
    metrics.append({"metric": "cells", "value": int(len(df))})
    metrics.append({"metric": "points_total", "value": float(pc.sum())})
    metrics.append({"metric": "points_mean", "value": float(pc.mean())})
    metrics.append({"metric": "points_std", "value": float(pc.std(ddof=0))})
    metrics.append({"metric": "points_p90", "value": float(pc.quantile(0.90))})
    metrics.append({"metric": "points_max", "value": float(pc.max())})
    # simple anomaly score: (value - mean) / std if std >0
    std = pc.std(ddof=0) or 1.0
    df["anomaly_score"] = (pc - pc.mean()) / std
    top_anoms = df.sort_values("anomaly_score", ascending=False).head(50)[
        ["h3", "point_count", "unique_trips", "anomaly_score"]
    ]
    # write metrics and anomalies into single CSV (long + anomalies) for flexibility
    metrics_df = pd.DataFrame(metrics)
    # Tag metrics vs anomalies
    metrics_df["kind"] = "metric"
    top_anoms.rename(columns={"point_count": "points"}, inplace=True)
    top_anoms["kind"] = "anomaly"
    out = pd.concat([metrics_df, top_anoms], ignore_index=True)
    out.to_csv(out_path, index=False)
    logger.info("Built anomaly_metrics artifact at %s", out_path)


def autobuild(artifacts_dir: Path, missing: list[str]) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if "stop_clusters" in missing:
        build_stop_clusters(artifacts_dir / "stop_clusters.csv")
    if "anomaly_metrics" in missing:
        build_anomaly_metrics(artifacts_dir / "anomaly_metrics.csv")
