from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["future"])


@router.get("/routes")
async def routes_stub():  # placeholder for Route Packages
    raise HTTPException(
        status_code=501,
        detail="Route Packages endpoint not implemented (future module)",
    )


@router.get("/hints")
async def hints_stub():  # placeholder for Choice Hints
    raise HTTPException(
        status_code=501, detail="Choice Hints endpoint not implemented (future module)"
    )


@router.get("/pricing")
async def pricing_stub():  # placeholder for Negotiation-friendly Pricing signals
    raise HTTPException(
        status_code=501, detail="Pricing endpoint not implemented (future module)"
    )
