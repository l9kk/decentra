from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...models.schemas import (
    CompareDestinationsRequest,
    CompareDestinationsResponse,
    AreaInsightsRequest,
    AreaInsightsResponse,
    DestinationRanking,
)
from ...services.hints_service import hints_service

router = APIRouter(tags=["future"])


@router.get("/routes")
async def routes_stub():  # placeholder for Route Packages
    raise HTTPException(
        status_code=501,
        detail="Route Packages endpoint not implemented (future module)",
    )


@router.post("/hints/compare", response_model=CompareDestinationsResponse)
async def compare_destinations(request: CompareDestinationsRequest):
    """
    Compare multiple destination options and get ML-based ranking by follow-on demand potential.

    Uses K-means clustering to identify destination types and predict follow-on ride opportunities.
    Helps drivers make informed decisions when they have multiple ride requests.
    """
    try:
        # Extract coordinates from request
        destinations = [(dest.lat, dest.lng) for dest in request.destinations]

        # Get ML-based rankings
        rankings = hints_service.compare_destinations(destinations)

        if not rankings:
            raise HTTPException(
                status_code=400,
                detail="Could not analyze destinations. Please try again.",
            )

        # Convert to response format
        destination_rankings = [DestinationRanking(**ranking) for ranking in rankings]

        return CompareDestinationsResponse(
            destinations=destination_rankings,
            ml_model_info={
                "algorithm": "KMeans",
                "clusters": 6,
                "features": ["location", "activity", "hub_proximity"],
                "trained": hints_service.ai_service._is_trained,
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error analyzing destinations: {str(e)}"
        )


@router.post("/hints/area", response_model=AreaInsightsResponse)
async def get_area_insights(request: AreaInsightsRequest):
    """
    Get detailed insights for a specific area including ML-based follow-on demand predictions.
    """
    try:
        insights = hints_service.get_area_insights(request.lat, request.lng)

        if "error" in insights:
            raise HTTPException(status_code=400, detail=insights["error"])

        return AreaInsightsResponse(**insights)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing area: {str(e)}")


@router.get("/pricing")
async def pricing_stub():  # placeholder for Negotiation-friendly Pricing signals
    raise HTTPException(
        status_code=501, detail="Pricing endpoint not implemented (future module)"
    )
