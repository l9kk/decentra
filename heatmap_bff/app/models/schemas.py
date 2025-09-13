from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class Center(BaseModel):
    lat: float
    lng: float


class CellOut(BaseModel):
    h3: str
    res: int
    point_count: int
    unique_trips: int
    value: Optional[int] = None
    share_points: float
    share_trips: float
    center: Center
    suppressed: bool
    schema_version: str
    # Optional intelligence fields
    score: Optional[float] = None
    score_quantile: Optional[float] = None


class MetaResolution(BaseModel):
    res: int
    cells_before: int
    cells_after_suppression: int
    total_points: int
    total_trips: int


class MetaOut(BaseModel):
    resolutions: List[MetaResolution]
    k_anon_default: int
    center: Center
    bbox: Optional[str]
    last_loaded_at: datetime


class HealthOut(BaseModel):
    status: str = "ok"
    resolutions: List[int]
    k_anon: int
    total_points: dict[int, int]
    total_trips: dict[int, int]
    center: Center


class ErrorOut(BaseModel):
    detail: str


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]
