# Mobility Heatmap BFF

## Quick Start

```bash
pip install -r requirements.txt
uvicorn heatmap_bff.app.main:app --reload
```

Base URL defaults to: `http://localhost:8000`

## Core Endpoints

- `GET /heatmap/meta` — dataset stats per resolution
- `GET /heatmap/cells` — live heatmap cells (json or geojson). Params: `res`, `format`, `polygon`, `include_suppressed`, `k`
- `GET /heatmap/forecast/meta` — forecast metadata for horizons
- `GET /heatmap/forecast/cells` — forecast cells (supports enrichment toggle)

## Forecast Endpoints (heuristic_v2)

Heuristic forecast derives short-horizon mobility intensity using a single snapshot of counts plus spatial intelligence (no historical timestamps). Provides per-horizon predicted counts and normalized `demand_index`.

### Meta

`GET /heatmap/forecast/meta?res=8&horizons=5,10,15`

Sample:

```json
{
  "generated_at": "2025-09-14T10:12:00Z",
  "res": 8,
  "horizons_minutes": [5, 10, 15],
  "forecast_version": "heuristic_v2",
  "cells_count": 12345,
  "k_anon_default": 20,
  "decay_base": 0.15,
  "quantiles": { "q50": 12, "q80": 34, "q95": 71 },
  "alpha_smoothing": 0.7,
  "corridor_boost": 0.1,
  "explanations": {
    "temporal_basis": "single-snapshot heuristic without historical timestamps",
    "components": [
      "variable_decay_tiers",
      "neighbor_smoothing",
      "corridor_short_horizon_boost",
      "hub_decay_clamp",
      "blended_demand_index",
      "tier_scaled_confidence_intervals"
    ]
  }
}
```

### Cells

`GET /heatmap/forecast/cells?res=8&horizons=5,15,30&format=json&include_enrichment=false`

Cell (when `include_enrichment=true`):

```json
{
  "h3": "8860e28d8bfffff",
  "current_count": 42,
  "unique_trips": 31,
  "suppressed": false,
  "is_hub": false,
  "is_corridor": true,
  "decay": 0.087,
  "predictions": {
    "5": {
      "predicted": 40.91,
      "lower": 33.2,
      "upper": 48.6,
      "demand_index": 0.73
    },
    "15": {
      "predicted": 38.12,
      "lower": 29.9,
      "upper": 46.3,
      "demand_index": 0.69
    },
    "30": {
      "predicted": 34.05,
      "lower": 25.5,
      "upper": 42.6,
      "demand_index": 0.62
    }
  }
}
```

If `include_enrichment=false`, the fields `is_hub`, `is_corridor`, `decay` are omitted.

`format=geojson&polygon=true` returns Polygon geometries; otherwise Points.

### Field Notes

- `decay_base`: global base exponential decay λ per hour.
- Per-cell `decay`: adjusted λ after tier + hub logic.
- `demand_index`: predicted / (0.5*max + 0.5*p95) for that horizon.
- Confidence interval width adapts by density tier.

### Frontend Tips

- Use `quantiles` to build legend buckets.
- Interpolate between provided horizons for smooth animation.
- Map `demand_index` via nonlinear scaling (sqrt) for color contrast.

## Privacy

k-anonymity suppression: cells with `point_count < k` or `unique_trips < k` have their value suppressed unless `include_suppressed=true`.

## Roadmap

- Optional corridor/hub metadata exposure in `/heatmap/meta`
- Persisted forecast parquet outputs
- Real temporal modeling once timestamps available

## License

Internal Hackathon Prototype.
