"""
Counterfactual Analysis Engine
================================
Answers: "What if intervention X is applied?"
Compares baseline vs intervention scenario.

Currently implements: ML-approximation mode.
API is designed for future SUMO simulation replacement.

Source label is ALWAYS included in results — 'ml_approximation' or 'sumo_simulation'.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CounterfactualEngine:
    """
    Computes counterfactual scenarios using ML approximation.
    The API contract is SUMO-compatible so the method can be 
    swapped later without changing the calling code.
    """

    def __init__(self, network_graph=None, predictor=None):
        self.graph = network_graph
        self.predictor = predictor  # TrafficPredictor instance

    def run_scenario(self,
                      segment_id: str,
                      intervention: dict,
                      current_features: pd.DataFrame,
                      horizon: str = "30m") -> dict:
        """
        Run a counterfactual scenario.

        Args:
            segment_id: target segment for intervention
            intervention: dict with 'intervention_type', 'capacity_delta_vph', etc.
            current_features: current feature DataFrame (all segments)
            horizon: forecast horizon ('15m', '30m', '45m', '60m')

        Returns:
            Counterfactual result with baseline vs intervention comparison.
        """
        seg_row = current_features[current_features["segment_id"] == segment_id]
        if seg_row.empty:
            return {"error": f"No data found for segment {segment_id}"}

        # Baseline prediction
        baseline = self._predict_baseline(seg_row, horizon)

        # Intervention: modify features to approximate effect
        modified_features = self._apply_intervention_to_features(
            current_features.copy(), segment_id, intervention
        )
        mod_row = modified_features[modified_features["segment_id"] == segment_id]

        # Intervention prediction
        intervention_pred = self._predict_baseline(mod_row, horizon)

        # Affected network
        affected_segments = []
        if self.graph:
            affected_segments = (
                self.graph.get_downstream_segments(segment_id, depth=2) +
                self.graph.get_neighboring_segments(segment_id)
            )
            affected_segments = list(set(affected_segments))[:15]

        # Compute deltas
        delta_congestion = baseline["congestion"] - intervention_pred["congestion"]
        delta_speed = intervention_pred["speed"] - baseline["speed"]
        delta_flow = intervention_pred["flow"] - baseline["flow"]

        return {
            "segment_id": segment_id,
            "horizon": horizon,
            "intervention": {
                "type": intervention.get("intervention_type", "unknown"),
                "capacity_delta_vph": intervention.get("capacity_delta_vph", 0),
                "description": self._describe_intervention(intervention),
            },
            "baseline": {
                "congestion_index": round(baseline["congestion"], 4),
                "speed_kmh": round(baseline["speed"], 2),
                "flow_vph": round(baseline["flow"], 1),
                "congestion_level": self._level(baseline["congestion"]),
            },
            "intervention_scenario": {
                "congestion_index": round(intervention_pred["congestion"], 4),
                "speed_kmh": round(intervention_pred["speed"], 2),
                "flow_vph": round(intervention_pred["flow"], 1),
                "congestion_level": self._level(intervention_pred["congestion"]),
            },
            "delta": {
                "congestion_reduction": round(delta_congestion, 4),
                "speed_improvement_kmh": round(delta_speed, 2),
                "flow_change_vph": round(delta_flow, 1),
                "congestion_reduction_pct": round(
                    delta_congestion / max(baseline["congestion"], 1e-6) * 100, 1
                ),
            },
            "affected_segments": affected_segments,
            "source": "ml_approximation",
            "confidence": 0.55,
            "disclaimer": (
                "This counterfactual is an ML-based approximation derived from "
                "capacity delta effects. It is NOT a simulation result. "
                "Use SUMO simulation for quantitative validation before operational decisions."
            )
        }

    def _predict_baseline(self, features_row: pd.DataFrame, horizon: str) -> dict:
        """Get baseline prediction for a segment."""
        if self.predictor is None:
            # Fallback: use current values
            row = features_row.iloc[0]
            return {
                "congestion": float(row.get("congestion_index", 0)),
                "speed": float(row.get("speed_kmh", 30)),
                "flow": float(row.get("flow_vph", 500)),
            }

        result = self.predictor.predict_segment(
            features_row.iloc[0]["segment_id"],
            features_row
        )
        h_key = f"+{horizon}"
        h_data = result.get("horizons", {}).get(h_key, {})
        return {
            "congestion": float(h_data.get("congestion", features_row.iloc[0].get("congestion_index", 0))),
            "speed": float(h_data.get("speed", features_row.iloc[0].get("speed_kmh", 30))),
            "flow": float(h_data.get("flow", features_row.iloc[0].get("flow_vph", 500))),
        }

    def _apply_intervention_to_features(self,
                                          features_df: pd.DataFrame,
                                          segment_id: str,
                                          intervention: dict) -> pd.DataFrame:
        """
        Approximate intervention effect on features.
        - capacity_upgrade → increase capacity_vph, reduce capacity_utilization
        - signal_retiming → slight speed improvement
        """
        mask = features_df["segment_id"] == segment_id
        int_type = intervention.get("intervention_type", "")
        cap_delta = float(intervention.get("capacity_delta_vph", 0))

        if "capacity_vph" in features_df.columns and cap_delta > 0:
            features_df.loc[mask, "capacity_vph"] = (
                features_df.loc[mask, "capacity_vph"] + cap_delta
            )
            if "capacity_utilization" in features_df.columns:
                flow = features_df.loc[mask, "flow_vph"]
                new_cap = features_df.loc[mask, "capacity_vph"]
                features_df.loc[mask, "capacity_utilization"] = (flow / new_cap).clip(0, 2.0)

        if int_type == "signal_retiming":
            if "speed_kmh" in features_df.columns:
                features_df.loc[mask, "speed_kmh"] = (
                    features_df.loc[mask, "speed_kmh"] * 1.05
                ).clip(upper=features_df.loc[mask, "free_flow_speed_kmh"]
                       if "free_flow_speed_kmh" in features_df.columns else 60)

        return features_df

    def _describe_intervention(self, intervention: dict) -> str:
        descriptions = {
            "capacity_upgrade": f"Add {intervention.get('capacity_delta_vph', 0)} vph capacity",
            "turn_lane": "Add dedicated turn lane",
            "signal_retiming": "Optimize signal timing",
            "lane_reversal": "Implement contraflow lane reversal",
            "ramp_metering": "Apply ramp metering control",
            "variable_speed_limit": "Implement variable speed limits",
        }
        return descriptions.get(intervention.get("intervention_type", ""), "Unknown intervention")

    def _level(self, congestion: float) -> str:
        if congestion >= 0.30:
            return "severe"
        elif congestion >= 0.15:
            return "heavy"
        elif congestion >= 0.05:
            return "moderate"
        return "free"
