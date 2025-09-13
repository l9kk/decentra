from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from ..core.config import get_settings


def get_settings_dep():  # simple alias for DI
    return get_settings()


def validate_resolution(res: int = Query(..., description="H3 resolution")) -> int:
    settings = get_settings()
    if res not in settings.supported_resolutions:
        raise HTTPException(status_code=400, detail="Unsupported resolution")
    return res
