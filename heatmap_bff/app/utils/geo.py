from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


@dataclass
class BBox:
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float

    def contains(self, lat: float, lng: float) -> bool:  # inclusive
        return self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.min_lat, self.min_lng, self.max_lat, self.max_lng


def parse_bbox(spec: str | None) -> Optional[BBox]:
    if spec is None or spec.strip() == "":
        return None
    parts = spec.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must have four comma-separated floats")
    try:
        vals = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError("bbox values must be floats") from e
    return BBox(*vals)  # type: ignore[arg-type]


def point_in_bbox(lat: float, lng: float, bbox: BBox | None) -> bool:
    if bbox is None:
        return True
    return bbox.contains(lat, lng)


def parse_bbox_query(param: str | None) -> Optional[BBox]:
    return parse_bbox(param)
