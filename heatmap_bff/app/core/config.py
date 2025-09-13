from __future__ import annotations

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    data_csv: str = Field(alias="DATA_CSV", default="./data/tracks.csv")
    precomputed_agg: str | None = Field(alias="PRECOMPUTED_AGG", default=None)
    artifacts_dir: str = Field(alias="ARTIFACTS_DIR", default="./outputs")
    auto_build_intel: bool = Field(alias="AUTO_BUILD_INTEL", default=False)
    default_h3_res: int = Field(alias="DEFAULT_H3_RES", default=8)
    suppress_k: int = Field(alias="SUPPRESS_K", default=20)
    city_center_lat: float = Field(alias="CITY_CENTER_LAT", default=51.169)
    city_center_lng: float = Field(alias="CITY_CENTER_LNG", default=71.449)
    astana_bbox: str | None = Field(alias="ASTANA_BBOX", default=None)
    allow_origins: str = Field(alias="ALLOW_ORIGINS", default="*")
    log_level: str = Field(alias="LOG_LEVEL", default="info")

    # Derived / fixed
    supported_resolutions: List[int] = [7, 8, 9]
    schema_version: str = "1.0.0"

    @validator("default_h3_res")
    def _validate_default_res(cls, v: int) -> int:
        if v not in [7, 8, 9]:
            raise ValueError("DEFAULT_H3_RES must be one of 7,8,9")
        return v

    @validator("suppress_k")
    def _validate_k(cls, v: int) -> int:
        if v < 1:
            raise ValueError("SUPPRESS_K must be >=1")
        return v

    @validator("astana_bbox")
    def _validate_bbox(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        parts = v.split(",")
        if len(parts) != 4:
            raise ValueError("ASTANA_BBOX must have four comma-separated numbers")
        try:
            _ = [float(p) for p in parts]
        except ValueError as e:
            raise ValueError("ASTANA_BBOX values must be floats") from e
        return v

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
