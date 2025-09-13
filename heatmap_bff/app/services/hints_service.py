"""
Hints Service for driver choice recommendations.
Provides ML-based ranking of destination options for drivers.
"""

from __future__ import annotations

import logging
from typing import List, Tuple
from dataclasses import asdict

from .ai_service import ai_service, DestinationScore


logger = logging.getLogger(__name__)


class HintsService:
    """Service for providing driver choice hints based on follow-on demand predictions."""

    def __init__(self):
        self.ai_service = ai_service

    def compare_destinations(
        self, destinations: List[Tuple[float, float]]
    ) -> List[dict]:
        """
        Compare multiple destinations and return ranked list with ML-based scoring.

        Args:
            destinations: List of (lat, lng) tuples representing potential destinations

        Returns:
            List of destination rankings with scores and explanations
        """
        if not destinations:
            return []

        # Ensure AI model is trained
        if not self.ai_service._is_trained:
            logger.info("Training AI model for first use...")
            if not self.ai_service.train_clustering_model():
                logger.error("Failed to train AI model")
                return self._fallback_scoring(destinations)

        # Get ML-based scores
        scores = self.ai_service.score_destinations(destinations)

        if not scores:
            logger.warning("No scores returned from AI service, using fallback")
            return self._fallback_scoring(destinations)

        # Convert to response format
        results = []
        for rank, score in enumerate(scores, 1):
            results.append(
                {
                    "rank": rank,
                    "lat": score.lat,
                    "lng": score.lng,
                    "score": round(score.total_score, 3),
                    "cluster_type": score.cluster_type.name,
                    "characteristics": score.cluster_type.characteristics,
                    "follow_on_probability": round(
                        score.cluster_type.avg_follow_on_demand, 3
                    ),
                    "current_activity": round(score.current_activity, 3),
                    "predicted_activity": round(score.predicted_activity, 3),
                    "hub_proximity_bonus": round(score.hub_proximity_bonus, 3),
                    "explanation": score.explanation,
                    "recommendation": self._generate_recommendation(score, rank),
                }
            )

        logger.info(f"Successfully ranked {len(results)} destinations")
        return results

    def _fallback_scoring(self, destinations: List[Tuple[float, float]]) -> List[dict]:
        """Fallback scoring when AI service is unavailable."""
        results = []
        for rank, (lat, lng) in enumerate(destinations, 1):
            # Simple distance-based scoring as fallback
            center_lat, center_lng = 51.169, 71.449  # Astana center
            distance_from_center = (
                (lat - center_lat) ** 2 + (lng - center_lng) ** 2
            ) ** 0.5
            score = max(
                0.1, 1.0 - distance_from_center * 10
            )  # Closer to center = higher score

            results.append(
                {
                    "rank": rank,
                    "lat": lat,
                    "lng": lng,
                    "score": round(score, 3),
                    "cluster_type": "Unknown",
                    "characteristics": "AI service unavailable - using fallback scoring",
                    "follow_on_probability": 0.3,
                    "current_activity": 0.2,
                    "predicted_activity": 0.2,
                    "hub_proximity_bonus": 0.0,
                    "explanation": "Fallback scoring based on distance from city center",
                    "recommendation": "Consider central locations for better follow-on opportunities",
                }
            )

        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)

        # Update ranks
        for rank, result in enumerate(results, 1):
            result["rank"] = rank

        return results

    def _generate_recommendation(self, score: DestinationScore, rank: int) -> str:
        """Generate a recommendation message based on the score."""
        if rank == 1:
            if score.cluster_type.avg_follow_on_demand > 0.7:
                return "🟢 Excellent choice! High chance of next ride"
            elif score.cluster_type.avg_follow_on_demand > 0.5:
                return "🟡 Good option with decent follow-on potential"
            else:
                return "🟠 Best of available options"
        elif rank == 2:
            return "🟡 Second choice - still good follow-on potential"
        else:
            return "🔴 Lower priority - consider other options if available"

    def get_area_insights(self, lat: float, lng: float) -> dict:
        """Get detailed insights for a specific area."""
        # Ensure AI model is trained
        if not self.ai_service._is_trained:
            if not self.ai_service.train_clustering_model():
                return {"error": "AI service unavailable"}

        # Get activity and predictions
        current_activity = self.ai_service._get_area_activity(lat, lng)
        cluster_type = self.ai_service.predict_destination_type(
            lat, lng, current_activity
        )
        hub_proximity = self.ai_service._calculate_hub_proximity(lat, lng)

        if cluster_type is None:
            return {"error": "Could not analyze area"}

        return {
            "lat": lat,
            "lng": lng,
            "cluster_type": cluster_type.name,
            "characteristics": cluster_type.characteristics,
            "follow_on_probability": round(cluster_type.avg_follow_on_demand, 3),
            "current_activity": round(current_activity, 3),
            "hub_proximity": round(hub_proximity, 3),
            "insights": self._generate_area_insights(
                cluster_type, current_activity, hub_proximity
            ),
        }

    def _generate_area_insights(
        self, cluster_type, activity: float, hub_proximity: float
    ) -> List[str]:
        """Generate actionable insights for an area."""
        insights = []

        if cluster_type.avg_follow_on_demand > 0.7:
            insights.append(
                "High follow-on demand area - excellent for continuous rides"
            )
        elif cluster_type.avg_follow_on_demand > 0.5:
            insights.append("Good follow-on potential - above average for next rides")
        else:
            insights.append(
                "Lower follow-on potential - may need to relocate after drop-off"
            )

        if hub_proximity > 0.1:
            insights.append(
                "Close to transport hub - increased passenger demand likely"
            )

        if activity > 0.7:
            insights.append("High activity zone - lots of movement and requests")
        elif activity < 0.3:
            insights.append("Quiet area - fewer ride requests expected")

        return insights


# Global instance
hints_service = HintsService()
