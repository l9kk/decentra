# Mobility Heatmap BFF (FastAPI)

Hackathon-focused FastAPI backend that serves privacy-preserving H3 heatmap aggregates for anonymized Astana mobility tracks (simplified: minimal layers, no test suite).

## Features

- H3 resolutions: 7, 8, 9 (default = env `DEFAULT_H3_RES`)
- Metrics: point_count, unique_trips
- Demand scoring heuristic (`score`, `score_quantile`) computed at load:
  - score = 0.6 _ normalized(point_count) + 0.4 _ (unique_trips / point_count)
  - quantile for quick ranking (currently internal; can be exposed easily)
- k-Anonymity suppression (point_count < k OR unique_trips < k)
- Optional inclusion of suppressed cells with `value=null`
- JSON or centroid GeoJSON output
- Weak ETag + `Cache-Control: public, max-age=60`
- Lean architecture (logic in route; future ideas left as stubs)
- Convenience endpoints: `/version`, `/heatmap/top`, `/admin/reload` (hackathon only, no auth)
- New intelligence endpoints (hackathon value-add):
  - `/corridors/top` (top OD links)
  - `/hubs/candidates` (candidate hub / stop clusters)
  - `/anomalies/summary` (data quality / anomaly stats)

## Quickstart

```bash
# 1. (Recommended) create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows Git Bash
# or: .venv\Scripts\activate  # cmd / PowerShell

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env  # adjust paths if needed

# 4. Build aggregates (if you only have raw CSV)
python -m heatmap_bff.scripts.build_precomputed --input geo_locations_astana_hackathon.csv --out outputs/h3_aggregates.csv --res 6 7 8 --k 5

# 5. Run server
uvicorn app.main:app --reload --port 8000
```

Visit: http://localhost:8000/docs

## Example Requests

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/heatmap/meta"
curl "http://localhost:8000/heatmap/cells?res=8&metric=trips&limit=50"
curl "http://localhost:8000/heatmap/cells?res=9&bbox=51.1,71.3,51.25,71.6&format=geojson&limit=500"
curl -X POST "http://localhost:8000/admin/reload"
curl "http://localhost:8000/heatmap/top?limit=25"
curl "http://localhost:8000/version"
curl "http://localhost:8000/corridors/top?limit=15"
curl "http://localhost:8000/hubs/candidates?limit=10"
curl "http://localhost:8000/anomalies/summary"
```

## deck.gl Snippet

```js
const data = await fetch("/heatmap/cells?res=8&metric=trips").then((r) =>
  r.json()
);
new deck.H3HexagonLayer({
  id: "hex",
  data,
  getHexagon: (d) => d.h3,
  getElevation: (d) => Math.log1p(d.value ?? 0),
  extruded: true,
  pickable: true,
  getFillColor: (d) => [255, 140 - Math.min(120, d.value ?? 0), 0, 200],
});
```

## Docker

```bash
docker build -t heatmap-bff .
docker run -p 8000:8000 heatmap-bff
```

Exposes API at `http://localhost:8000`.

## Project Structure

```
app/
  api/
    routes/
      system.py       # root, health, version, reload
      heatmap.py      # heatmap meta/cells/top
      intelligence.py # corridors, hubs, anomalies
      future_stubs.py # placeholders (still present)
    deps.py           # shared dependency functions
  core/               # config & logging
  repositories/       # data loading + in-memory aggregates
  models/             # pydantic schemas
  utils/              # geo helpers only (hashing removed)
  main.py             # app factory + extra endpoints
```

## Documentation

See `/docs` folder:

- 01_HACKATHON_CONTEXT.md
- 02_DATASET.md
- 03_PRIVACY.md
- 04_API.md
- 05_UI_INTEGRATION.md
- 06_ROADMAP.md

## Future Modules (Planned)

Route Packages, Choice Hints, Anomalies/Safety, Negotiation-friendly Pricing (not implemented in hackathon version).

## Limitations (Hackathon Build)

- Static snapshot unless `/admin/reload` called.
- No authentication / roles.
- No predictive time-series uplift yet (roadmap ready).
- Simplified error handling (generic 500 JSON).

## Pitch Narrative (Use in Demo)

"We ingest anonymized raw mobility traces and transform them into a privacy-safe spatial intelligence layer: live demand surfaces (H3), high-value corridors, hub candidate sites and anomaly quality signals. A lightweight scoring engine ranks micro-areas for operational focus while preserving user privacy via k-anonymity suppression."

## Using Official Judge Dataset Artifacts

Place provided or generated CSV artifacts (e.g. `h3_aggregates.csv`, `od_top.csv`, `stop_clusters.csv`, `anomaly_metrics.csv`) into a directory (default `./outputs`).

Two modes of operation:

1. Precomputed Aggregates (recommended for speed):

- Set in `.env`:
  - `PRECOMPUTED_AGG=./outputs/h3_aggregates.csv`
  - (Optional) `ARTIFACTS_DIR=./outputs`
- The server will skip raw aggregation and directly load per-resolution data.

2. Raw Re-Aggregation:

- Provide raw mobility CSV via `DATA_CSV=./data/tracks.csv` (or another path).
- This will recompute H3 aggregates on startup (slower; only needed if judging requires demonstration of processing pipeline).

`ARTIFACTS_DIR` is used to discover optional intelligence sources (auto-built if missing and `AUTO_BUILD_INTEL=1`):

- `od_top.csv`
- `stop_clusters.csv`
- `anomaly_metrics.csv`

Missing files are silently ignored; corresponding endpoints will just return empty arrays.

---

MIT License.
