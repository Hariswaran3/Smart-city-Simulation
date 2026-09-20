"""
Intervention Recommendation Engine
=====================================
Ranks planning candidates by estimated benefit given current and forecast conditions.
Returns candidate interventions — NOT 'optimal' solutions.
Labels all outputs as estimates with confidence levels.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

INTERVENTION_BASE_BENEFIT = {
    "capacity_upgrade": 0.35,
    "turn_lane": 0.20,
    "signal_retiming": 0.18,
    "lane_reversal": 0.25,
    "ramp_metering": 0.22,
    "variable_speed_limit": 0.15,
}

FEASIBILITY_SCORE = {
    "low": 0.9,    # easier to implement
    "medium": 0.6,
    "high": 0.3,   # harder to implement
}


class InterventionEngine:
    """
    Ranks planning candidates by estimated impact on congestion.
    Uses current congestion + forecast + capacity delta.
    All outputs are labeled as ESTIMATES — not guaranteed improvements.
    """

    def __init__(self, network_graph=None, current_congestion: Optional[Dict[str, float]] = None):
        self.graph = network_graph
        self.current_congestion = current_congestion or {}

    def update_congestion(self, congestion_map: Dict[str, float]):
        self.current_congestion = congestion_map

    def score_candidate(self,
                         candidate: dict,
                         forecast_congestion: Optional[Dict[str, float]] = None,
                         network_df: Optional[pd.DataFrame] = None) -> dict:
        """
        Score a single planning candidate.

        Args:
            candidate: row from planning_candidates.csv as dict
            forecast_congestion: dict seg_id → predicted congestion_index (15min)
            network_df: network DataFrame for capacity lookup

        Returns:
            Scored candidate dict with estimated benefit and confidence.
        """
        seg_id = candidate.get("target_segment", "")
        int_type = candidate.get("intervention_type", "")
        cap_delta = float(candidate.get("capacity_delta_vph", 0))
        cost_idx = float(candidate.get("cost_index", 5))
        feasibility_band = candidate.get("feasibility_band", "medium")

        # Current and forecast congestion
        curr_cong = self.current_congestion.get(seg_id, 0.0)
        fore_cong = (forecast_congestion or {}).get(seg_id, curr_cong)

        # Network capacity
        seg_capacity = 1800.0  # default
        if self.graph:
            info = self.graph.get_segment_info(seg_id)
            if info:
                seg_capacity = info.capacity_vph

        # Demand pressure: how urgently is this intervention needed?
        demand_pressure = max(curr_cong, fore_cong)

        # Base benefit from intervention type
        base_benefit = INTERVENTION_BASE_BENEFIT.get(int_type, 0.15)

        # Capacity-relative benefit
        cap_benefit = min(0.5, cap_delta / max(seg_capacity, 1))

        # Feasibility factor
        feasibility_score = FEASIBILITY_SCORE.get(feasibility_band, 0.5)

        # Cost-effectiveness (higher benefit per cost unit → better)
        total_benefit = (base_benefit * 0.4 + cap_benefit * 0.3 + demand_pressure * 0.3)
        cost_effectiveness = total_benefit / max(cost_idx, 1) * 10

        # Priority: high-demand + high-feasibility + low-cost wins
        priority_score = (
            demand_pressure * 0.35 +
            feasibility_score * 0.25 +
            cap_benefit * 0.20 +
            base_benefit * 0.20
        ) * (1 - min(0.4, cost_idx / 20.0))

        # Predicted congestion reduction (rough estimate, not simulation-validated)
        pred_reduction = total_benefit * demand_pressure * 0.6

        # Affected network
        affected_network = []
        if self.graph and seg_id:
            affected_network = (
                self.graph.get_downstream_segments(seg_id, depth=2) +
                self.graph.get_neighboring_segments(seg_id)
            )
            affected_network = list(set(affected_network))[:15]

        confidence = min(0.75, 0.4 + demand_pressure * 0.4 + feasibility_score * 0.15)

        return {
            "candidate_id": candidate.get("candidate_id", ""),
            "segment_id": seg_id,
            "intervention_type": int_type,
            "feasibility_band": feasibility_band,
            "capacity_delta_vph": cap_delta,
            "cost_index": cost_idx,
            "current_congestion": round(curr_cong, 4),
            "forecast_congestion_15m": round(fore_cong, 4),
            "demand_pressure": round(demand_pressure, 4),
            "predicted_congestion_reduction": round(pred_reduction, 4),
            "estimated_benefit_score": round(total_benefit, 4),
            "cost_effectiveness": round(cost_effectiveness, 4),
            "feasibility_score": round(feasibility_score, 3),
            "priority_score": round(priority_score, 4),
            "affected_network": affected_network,
            "confidence": round(confidence, 2),
            "disclaimer": (
                "This is a candidate intervention with estimated impact. "
                "Predicted congestion reduction is an approximation based on "
                "capacity delta and current traffic pressure. "
                "Requires SUMO simulation or field trial for validation."
            )
        }

    def rank_candidates(self,
                         candidates_df: pd.DataFrame,
                         forecast_congestion: Optional[Dict[str, float]] = None,
                         network_df: Optional[pd.DataFrame] = None,
                         top_n: int = 20) -> List[dict]:
        """
        Score and rank all planning candidates.
        Returns top_n candidates sorted by priority_score descending.
        """
        scored = []
        for _, row in candidates_df.iterrows():
            score = self.score_candidate(row.to_dict(), forecast_congestion, network_df)
            scored.append(score)

        scored.sort(key=lambda x: -x["priority_score"])
        return scored[:top_n]

    def get_interventions_for_segment(self,
                                       segment_id: str,
                                       candidates_df: pd.DataFrame,
                                       forecast_congestion: Optional[Dict[str, float]] = None) -> List[dict]:
        """Return all interventions for a specific segment."""
        seg_candidates = candidates_df[candidates_df["target_segment"] == segment_id]
        results = []
        for _, row in seg_candidates.iterrows():
            score = self.score_candidate(row.to_dict(), forecast_congestion)
            results.append(score)
        results.sort(key=lambda x: -x["priority_score"])
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys, json
    sys.path.insert(0, r"d:\data-urban\traffic-intelligence")
    from ml.preprocessing.data_loader import load_planning_candidates, load_traffic
    from backend.core.network_graph import get_network_graph
    from backend.intelligence.congestion_propagation import build_congestion_map

    g = get_network_graph()
    traffic = load_traffic("validation")
    cong_map = build_congestion_map(traffic)
    candidates = load_planning_candidates()

    engine = InterventionEngine(g, cong_map)
    ranked = engine.rank_candidates(candidates, cong_map, top_n=5)
    print("Top 5 intervention candidates:")
    for r in ranked:
        print(f"  {r['candidate_id']} ({r['segment_id']}): {r['intervention_type']} "
              f"priority={r['priority_score']:.3f} conf={r['confidence']:.2f}")
