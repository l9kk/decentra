from __future__ import annotations
import argparse
import pandas as pd
import h3
from pathlib import Path
import sys

# Minimal standalone builder (not relying on FastAPI runtime)

REQUIRED_COLUMNS = ["randomized_id", "lat", "lng"]


def build(input_csv: Path, out_csv: Path, resolutions: list[int], k: int) -> None:
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    # Stream in chunks to avoid memory blow-up
    accum: dict[int, dict[str, dict]] = {r: {} for r in resolutions}
    for chunk in pd.read_csv(input_csv, chunksize=250_000):
        missing = [c for c in REQUIRED_COLUMNS if c not in chunk.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        chunk = chunk.dropna(subset=["randomized_id", "lat", "lng"])
        if chunk.empty:
            continue
        lats = chunk["lat"].to_numpy()
        lngs = chunk["lng"].to_numpy()
        ids = chunk["randomized_id"].astype(str).to_numpy()
        for res in resolutions:
            cells = [
                h3.latlng_to_cell(la, ln, res)
                for la, ln in zip(lats, lngs, strict=False)
            ]
            for cell, trip in zip(cells, ids, strict=False):
                bucket = accum[res].setdefault(cell, {"points": 0, "ids": set()})
                bucket["points"] += 1
                bucket["ids"].add(trip)
    # Finalize rows
    rows = []
    for res, mapping in accum.items():
        for cell, data in mapping.items():
            lat_center, lng_center = h3.cell_to_latlng(cell)
            point_count = data["points"]
            unique_trips = len(data["ids"])
            rows.append(
                {
                    "h3": cell,
                    "res": res,
                    "point_count": point_count,
                    "unique_trips": unique_trips,
                    "lat_center": lat_center,
                    "lng_center": lng_center,
                }
            )
    if not rows:
        raise RuntimeError("No data aggregated; check input file")
    df = pd.DataFrame(rows)
    # Demand score heuristic
    max_points = df["point_count"].max() or 1
    df["_trip_intensity"] = df["point_count"] / max_points
    df["_uniq_factor"] = (df["unique_trips"] / df["point_count"].clip(lower=1)).clip(
        0, 1
    )
    df["score"] = 0.6 * df["_trip_intensity"] + 0.4 * df["_uniq_factor"]
    df["score_quantile"] = df["score"].rank(pct=True)
    df.drop(columns=["_trip_intensity", "_uniq_factor"], inplace=True)
    # Suppression flag only (runtime decides filtering)
    df["suppressed"] = (df["point_count"] < k) | (df["unique_trips"] < k)
    df.sort_values(["res", "point_count"], ascending=[True, False], inplace=True)
    df.to_csv(out_csv, index=False)
    print(f"Wrote {len(df)} rows to {out_csv}")


def parse_args(argv: list[str]):
    ap = argparse.ArgumentParser(description="Build precomputed H3 aggregates")
    ap.add_argument("--input", required=True, help="Raw mobility CSV path")
    ap.add_argument("--out", required=True, help="Output aggregates CSV path")
    ap.add_argument(
        "--res", nargs="+", type=int, default=[6, 7, 8], help="H3 resolutions"
    )
    ap.add_argument("--k", type=int, default=5, help="Suppression k threshold")
    return ap.parse_args(argv)


def main(argv: list[str]):
    args = parse_args(argv)
    build(Path(args.input), Path(args.out), args.res, args.k)


if __name__ == "__main__":
    main(sys.argv[1:])
