from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from ..core.config import get_settings
from ..intel import builder

logger = logging.getLogger(__name__)

# Expected filenames (simple CSV forms)
ARTIFACT_FILES = {
    "od_top": "od_top.csv",  # top OD pairs
    "stop_clusters": "stop_clusters.csv",  # cluster centroids
    "anomaly_metrics": "anomaly_metrics.csv",  # anomaly summary metrics
}

_cache: Dict[str, pd.DataFrame] = {}


def _try_load(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if df.empty:
            return None
        return df
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed loading artifact %s: %s", path, e)
        return None


def preload() -> None:
    """Preload optional artifacts using configured ARTIFACTS_DIR.

    Missing files are silently ignored; loaded set is logged.
    """
    settings = get_settings()
    base_dir = Path(settings.artifacts_dir)
    global _cache
    loaded = []
    missing = []
    for key, fname in ARTIFACT_FILES.items():
        path = base_dir / fname
        df = _try_load(path)
        if df is not None:
            _cache[key] = df
            loaded.append(str(path))
        else:
            missing.append(key)
    # Auto-build selected artifacts if configured
    if missing and settings.auto_build_intel:
        builder.autobuild(base_dir, missing)
        # attempt reload of those built
        for key in list(missing):
            fname = ARTIFACT_FILES[key]
            path = base_dir / fname
            df_new = _try_load(path)
            if df_new is not None:
                _cache[key] = df_new
                loaded.append(str(path))
    if loaded:
        logger.info("Loaded optional artifacts: %s", ", ".join(loaded))
    else:
        logger.info("No optional artifacts loaded (none found in %s)", base_dir)


def get(name: str) -> Optional[pd.DataFrame]:
    key = name.lower().replace(".csv", "").strip()
    return _cache.get(key)


def status() -> dict:
    """Return a lightweight status summary for each known artifact."""
    settings = get_settings()
    base_dir = Path(settings.artifacts_dir)
    summary = {}
    for key, fname in ARTIFACT_FILES.items():
        path = base_dir / fname
        df = _cache.get(key)
        summary[key] = {
            "present": df is not None,
            "rows": (int(len(df)) if df is not None else 0),
            "path": str(path),
        }
    summary["auto_build_enabled"] = settings.auto_build_intel
    return summary
