"""
AI Service for ML-based destination clustering and predictions.
Provides clustering model for destination types and follow-on demand scoring.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import math

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import h3

from ..core.config import get_settings
from ..repositories.aggregates_repo import aggregates_repo


logger = logging.getLogger(__name__)


@dataclass
class DestinationType:
    """Represents a learned destination cluster type."""

    cluster_id: int
    name: str
    avg_follow_on_demand: float
    characteristics: str


@dataclass
class DestinationScore:
    """Score for a single destination."""

    lat: float
    lng: float
    cluster_type: DestinationType
    current_activity: float
    predicted_activity: float
    hub_proximity_bonus: float
    total_score: float
    explanation: str


class AIService:
    """ML service for destination clustering and demand prediction."""

    def __init__(self):
        self._model: Optional[KMeans] = None
        self._scaler: Optional[StandardScaler] = None
        self._cluster_types: Dict[int, DestinationType] = {}
        self._hubs: Set[Tuple[float, float]] = set()
        self._is_trained = False

    def _load_hubs(self) -> None:
        """Load transport hubs from stop_clusters.csv."""
        try:
            df = pd.read_csv("outputs/stop_clusters.csv")
            # Take top hubs by importance
            df = df.sort_values("importance", ascending=False).head(20)
            self._hubs = {
                (row["lat"], row["lng"]) for _, row in df.iterrows()
            }
            logger.info(f"Loaded {len(self._hubs)} transport hubs")
        except Exception as e:
            logger.warning(f"Could not load hubs: {e}")
            self._hubs = set()
    def _calculate_hub_proximity(self, lat: float, lng: float) -> float:
        """Calculate proximity bonus based on distance to nearest hub."""
        if not self._hubs:
            return 0.0

        min_distance = float("inf")
        for hub_lat, hub_lng in self._hubs:
            # Simple distance calculation (good enough for hackathon)
            distance = math.sqrt((lat - hub_lat) ** 2 + (lng - hub_lng) ** 2)
            min_distance = min(min_distance, distance)

        # Convert to proximity bonus (higher = closer to hub)
        # Max bonus of 0.3 for very close to hub, decreasing with distance
        proximity_bonus = max(0, 0.3 * math.exp(-min_distance * 100))
        return proximity_bonus

    def _prepare_training_data(self, res: int = 8) -> pd.DataFrame:
        try:
            resolution_data = aggregates_repo.get_resolution(res)
        except KeyError:
            logger.error(f"No aggregates for resolution {res}")
            return pd.DataFrame()

        # Get data through the repository interface
        df = aggregates_repo.get_resolution(res).df.copy()

        # Calculate activity level (normalized)
        max_points = df["point_count"].max() if len(df) > 0 else 1
        df["activity_level"] = df["point_count"] / max_points

        # Calculate hub proximity for each cell
        df["hub_proximity"] = df.apply(
            lambda row: self._calculate_hub_proximity(
                row["lat_center"], row["lng_center"]
            ),
            axis=1,
        )

        # Prepare features for clustering
        features_df = df[
            ["lat_center", "lng_center", "activity_level", "hub_proximity"]
        ].copy()
        features_df = features_df.dropna()

        logger.info(f"Prepared {len(features_df)} samples for training")
        return features_df

    def train_clustering_model(self, n_clusters: int = 6) -> bool:
        """Train KMeans model to identify destination types."""
        try:
            # Load hubs data
            self._load_hubs()

            # Prepare training data
            training_data = self._prepare_training_data()
            if len(training_data) < n_clusters:
                logger.error(f"Not enough data for {n_clusters} clusters")
                return False

            # Prepare features
            features = training_data[
                ["lat_center", "lng_center", "activity_level", "hub_proximity"]
            ]

            # Scale features
            self._scaler = StandardScaler()
            features_scaled = self._scaler.fit_transform(features)

            # Train KMeans
            self._model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = self._model.fit_predict(features_scaled)

            # Analyze clusters to create destination types
            training_data["cluster"] = cluster_labels
            self._analyze_clusters(training_data)

            self._is_trained = True
            logger.info(
                f"Successfully trained clustering model with {n_clusters} clusters"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to train clustering model: {e}")
            return False

    def _analyze_clusters(self, data: pd.DataFrame) -> None:
        """Analyze clusters to create meaningful destination types."""
        self._cluster_types = {}

        for cluster_id in data["cluster"].unique():
            cluster_data = data[data["cluster"] == cluster_id]

            # Calculate cluster characteristics
            avg_activity = cluster_data["activity_level"].mean()
            avg_hub_proximity = cluster_data["hub_proximity"].mean()
            cluster_size = len(cluster_data)

            # Determine cluster type based on characteristics
            if avg_hub_proximity > 0.1:
                name = "Transport Hub Area"
                follow_on_demand = (
                    0.8 + avg_activity * 0.2
                )  # High base + activity bonus
                characteristics = "Near major transport hubs, high follow-on demand"
            elif avg_activity > 0.7:
                name = "High Activity Zone"
                follow_on_demand = 0.7 + avg_activity * 0.2
                characteristics = "Dense activity area, good follow-on potential"
            elif avg_activity > 0.3:
                name = "Moderate Activity Area"
                follow_on_demand = 0.4 + avg_activity * 0.3
                characteristics = "Moderate activity, average follow-on demand"
            else:
                name = "Low Activity Zone"
                follow_on_demand = 0.1 + avg_activity * 0.2
                characteristics = "Quiet area, lower follow-on potential"

            self._cluster_types[cluster_id] = DestinationType(
                cluster_id=cluster_id,
                name=name,
                avg_follow_on_demand=follow_on_demand,
                characteristics=characteristics,
            )

            logger.info(
                f"Cluster {cluster_id}: {name} (size: {cluster_size}, follow-on: {follow_on_demand:.2f})"
            )

    def predict_destination_type(
        self, lat: float, lng: float, activity: float
    ) -> Optional[DestinationType]:
        """Predict destination type for given coordinates."""
        if not self._is_trained or self._model is None or self._scaler is None:
            return None

        try:
            # Calculate hub proximity
            hub_proximity = self._calculate_hub_proximity(lat, lng)

            # Prepare features
            features = np.array([[lat, lng, activity, hub_proximity]])
            features_scaled = self._scaler.transform(features)

            # Predict cluster
            cluster_id = self._model.predict(features_scaled)[0]

            return self._cluster_types.get(cluster_id)

        except Exception as e:
            logger.error(f"Failed to predict destination type: {e}")
            return None

    def score_destinations(
        self, destinations: List[Tuple[float, float]]
    ) -> List[DestinationScore]:
        """Score multiple destinations and return ranked list."""
        if not self._is_trained:
            # Train model if not already trained
            if not self.train_clustering_model():
                logger.error("Could not train model for scoring")
                return []

        scores = []

        for lat, lng in destinations:
            try:
                # Get current activity (simplified - use nearby H3 cell)
                current_activity = self._get_area_activity(lat, lng)

                # Get predicted activity (simplified - use current + small boost)
                predicted_activity = current_activity * 1.1  # Simple prediction

                # Get cluster prediction
                cluster_type = self.predict_destination_type(lat, lng, current_activity)
                if cluster_type is None:
                    # Fallback scoring
                    cluster_type = DestinationType(
                        cluster_id=-1,
                        name="Unknown Area",
                        avg_follow_on_demand=0.3,
                        characteristics="No cluster data available",
                    )

                # Calculate hub proximity bonus
                hub_bonus = self._calculate_hub_proximity(lat, lng)

                # Calculate total score
                total_score = (
                    current_activity * 0.3
                    + predicted_activity * 0.2
                    + cluster_type.avg_follow_on_demand * 0.4
                    + hub_bonus * 0.1
                )

                # Generate explanation
                explanation = f"{cluster_type.name} - {cluster_type.characteristics}"

                scores.append(
                    DestinationScore(
                        lat=lat,
                        lng=lng,
                        cluster_type=cluster_type,
                        current_activity=current_activity,
                        predicted_activity=predicted_activity,
                        hub_proximity_bonus=hub_bonus,
                        total_score=total_score,
                        explanation=explanation,
                    )
                )

            except Exception as e:
                logger.error(f"Failed to score destination ({lat}, {lng}): {e}")
                continue

        # Sort by score (highest first)
        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores

    def _get_area_activity(self, lat: float, lng: float, res: int = 8) -> float:
        """Get activity level for a location (simplified implementation)."""
        try:
            # Get H3 cell for location
            h3_cell = h3.latlng_to_cell(lat, lng, res)

            # Look up in aggregates
            if res in aggregates_repo.aggregates:
                df = aggregates_repo.aggregates[res]
                cell_data = df[df["h3"] == h3_cell]
                if len(cell_data) > 0:
                    # Normalize activity
                    max_points = df["point_count"].max()
                    return (
                        cell_data.iloc[0]["point_count"] / max_points
                        if max_points > 0
                        else 0.0
                    )

            return 0.1  # Default low activity

        except Exception:
            return 0.1


# Global instance
ai_service = AIService()
