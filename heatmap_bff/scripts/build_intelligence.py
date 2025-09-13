from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd
try:
    from heatmap_bff.app.intel import builder  # normal package import
except ModuleNotFoundError:  # fallback if executed as plain script without -m
    import sys, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from heatmap_bff.app.intel import builder  # retry

# This script regenerates intelligence artifacts from an existing aggregates CSV.
# It writes stop_clusters.csv and anomaly_metrics.csv to the target directory.

def parse_args(argv: list[str]):
    ap = argparse.ArgumentParser(description="Build intelligence artifacts from aggregates CSV")
    ap.add_argument('--aggregates', required=True, help='Path to h3_aggregates.csv')
    ap.add_argument('--out', required=True, help='Artifacts output directory')
    ap.add_argument('--top-cells', type=int, default=200, help='Top scoring cells used for hubs')
    return ap.parse_args(argv)


def main(argv: list[str]):
    args = parse_args(argv)
    agg_path = Path(args.aggregates)
    if not agg_path.exists():
        raise FileNotFoundError(f"Aggregates file not found: {agg_path}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(agg_path)
    if df.empty:
        raise RuntimeError("Aggregates CSV is empty")
    # Use highest resolution slice
    max_res = int(df['res'].max())
    df_high = df[df['res'] == max_res].copy()
    if 'score' not in df_high.columns:
        # Derive score if missing
        max_points = df_high['point_count'].max() or 1
        df_high['_trip_intensity'] = df_high['point_count'] / max_points
        df_high['_uniq_factor'] = (df_high['unique_trips'] / df_high['point_count'].clip(lower=1)).clip(0,1)
        df_high['score'] = 0.6*df_high['_trip_intensity'] + 0.4*df_high['_uniq_factor']
        df_high['score_quantile'] = df_high['score'].rank(pct=True)
        df_high.drop(columns=['_trip_intensity','_uniq_factor'], inplace=True)
    # Build stop clusters via existing builder logic
    builder.build_stop_clusters(df_high, out_dir / 'stop_clusters.csv', top_n=args.top_cells)
    # Build anomaly metrics
    builder.build_anomaly_metrics(df_high, out_dir / 'anomaly_metrics.csv')
    print(f"Wrote stop_clusters.csv and anomaly_metrics.csv to {out_dir}")

if __name__ == '__main__':
    main(sys.argv[1:])
