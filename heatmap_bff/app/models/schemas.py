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


class DestinationInput(BaseModel):
    lat: float = Field(..., description="Latitude coordinate")
    lng: float = Field(..., description="Longitude coordinate")


class CompareDestinationsRequest(BaseModel):
    destinations: List[DestinationInput] = Field(
        ...,
        description="List of potential destinations to compare",
        min_items=1,
        max_items=10,
    )


class DestinationRanking(BaseModel):
    rank: int = Field(..., description="Ranking position (1 = best)")
    lat: float
    lng: float
    score: float = Field(..., description="Overall follow-on demand score (0-1)")
    cluster_type: str = Field(..., description="ML-identified destination type")
    characteristics: str = Field(..., description="Area characteristics")
    follow_on_probability: float = Field(
        ..., description="Probability of getting next ride (0-1)"
    )
    current_activity: float = Field(..., description="Current activity level (0-1)")
    predicted_activity: float = Field(..., description="Predicted activity level (0-1)")
    hub_proximity_bonus: float = Field(
        ..., description="Transport hub proximity bonus (0-1)"
    )
    explanation: str = Field(..., description="Human-readable explanation")
    recommendation: str = Field(..., description="Recommendation for driver")


class CompareDestinationsResponse(BaseModel):
    destinations: List[DestinationRanking]
    ml_model_info: dict = Field(
        default={
            "algorithm": "KMeans",
            "clusters": 6,
            "features": ["location", "activity", "hub_proximity"],
        },
        description="Information about the ML model used",
    )


class AreaInsightsRequest(BaseModel):
    lat: float = Field(..., description="Latitude coordinate")
    lng: float = Field(..., description="Longitude coordinate")


class AreaInsightsResponse(BaseModel):
    lat: float
    lng: float
    cluster_type: str
    characteristics: str
    follow_on_probability: float
    current_activity: float
    hub_proximity: float
    insights: List[str] = Field(..., description="Actionable insights for drivers")
