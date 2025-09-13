from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
import pandas as pd


@dataclass
class ResolutionAggregate:
    res: int
    df: pd.DataFrame  # columns: h3, res, point_count, unique_trips, lat_center, lng_center
    total_points: int
    total_trips: int


class AggregatesRepository:
    def __init__(self) -> None:
        self._store: Dict[int, ResolutionAggregate] = {}
        self.loaded_at: datetime | None = None

    def set_resolution(self, agg: ResolutionAggregate) -> None:
        self._store[agg.res] = agg
        if self.loaded_at is None:
            self.loaded_at = datetime.utcnow()

    def get_resolution(self, res: int) -> ResolutionAggregate:
        if res not in self._store:
            raise KeyError(f"Resolution {res} not loaded")
        return self._store[res]

    def resolutions(self) -> List[int]:
        return sorted(self._store.keys())

    def totals_points(self) -> dict[int, int]:
        return {r: agg.total_points for r, agg in self._store.items()}

    def totals_trips(self) -> dict[int, int]:
        return {r: agg.total_trips for r, agg in self._store.items()}


aggregates_repo = AggregatesRepository()
