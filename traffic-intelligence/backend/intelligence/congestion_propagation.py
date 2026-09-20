"""
Congestion Propagation Analysis
================================
Given a congested origin segment, determines which upstream, downstream,
and neighboring segments are likely to be affected.

Clearly distinguishes:
  - observed: segments already showing elevated congestion
  - network_inference: graph-topology-based affected segments
  - model_prediction: ML-predicted congestion values

Does NOT claim causal proof — uses correlation + network structure.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CONGESTION_THRESHOLD_MODERATE = 0.05
CONGESTION_THRESHOLD_HEAVY = 0.15
CONGESTION_THRESHOLD_SEVERE = 0.30


def propagation_severity(congestion_index: float) -> str:
    if congestion_index >= CONGESTION_THRESHOLD_SEVERE:
        return "severe"
    elif congestion_index >= CONGESTION_THRESHOLD_HEAVY:
        return "heavy"
    elif congestion_index >= CONGESTION_THRESHOLD_MODERATE:
        return "moderate"
    return "free"


class CongestionPropagationAnalyzer:
    """
    Analyzes congestion propagation from an origin segment.
    Uses network topology + current observed/predicted congestion.
    """

    def __init__(self, network_graph, current_congestion: Optional[Dict[str, float]] = None):
        """
        Args:
            network_graph: TrafficNetworkGraph instance
            current_congestion: dict mapping segment_id → current congestion_index
        """
        self.graph = network_graph
        self.current_congestion = current_congestion or {}

    def update_congestion(self, congestion_map: Dict[str, float]):
        """Update current congestion state."""
        self.current_congestion = congestion_map

    def analyze(self,
                 origin_segment: str,
                 max_depth: int = 3,
                 congestion_decay: float = 0.7,
                 predictions: Optional[Dict[str, Dict]] = None) -> dict:
        """
        Analyze congestion propagation from origin_segment.

        Args:
            origin_segment: starting segment ID
            max_depth: maximum graph traversal depth
            congestion_decay: per-hop severity decay factor
            predictions: optional dict {segment_id: {horizon: congestion_index}}

        Returns:
            Propagation analysis result with affected segments and confidence.
        """
        origin_congestion = self.current_congestion.get(origin_segment, 0.0)
        origin_severity = propagation_severity(origin_congestion)

        if origin_congestion < CONGESTION_THRESHOLD_MODERATE:
            return {
                "origin_segment": origin_segment,
                "origin_congestion": origin_congestion,
                "origin_severity": origin_severity,
                "affected_segments": [],
                "propagation_depth": 0,
                "severity": "none",
                "confidence": 0.9,
                "method": "network_inference",
                "note": "Origin segment congestion below threshold — no significant propagation expected."
            }

        affected = {}

        # Upstream: traffic queues back from a bottleneck
        upstream_segs = self.graph.get_upstream_segments(origin_segment, depth=max_depth)
        for i, seg in enumerate(upstream_segs):
            depth = i + 1
            hop_decay = congestion_decay ** depth
            estimated_congestion = origin_congestion * hop_decay
            observed = self.current_congestion.get(seg, 0.0)
            affected[seg] = {
                "segment_id": seg,
                "direction": "upstream",
                "hop_depth": depth,
                "estimated_congestion": round(estimated_congestion, 4),
                "observed_congestion": round(observed, 4),
                "severity": propagation_severity(max(estimated_congestion, observed * 0.5)),
                "propagation_type": "queue_spillback",
                "source": "network_inference",
                "confidence": round(max(0.3, 0.9 - depth * 0.15), 2),
            }

        # Downstream: high flow may push congestion forward
        downstream_segs = self.graph.get_downstream_segments(origin_segment, depth=max_depth)
        for i, seg in enumerate(downstream_segs):
            depth = i + 1
            hop_decay = (congestion_decay * 0.6) ** depth  # downstream propagates slower
            estimated_congestion = origin_congestion * hop_decay
            observed = self.current_congestion.get(seg, 0.0)
            affected[seg] = {
                "segment_id": seg,
                "direction": "downstream",
                "hop_depth": depth,
                "estimated_congestion": round(estimated_congestion, 4),
                "observed_congestion": round(observed, 4),
                "severity": propagation_severity(max(estimated_congestion, observed * 0.3)),
                "propagation_type": "flow_pressure",
                "source": "network_inference",
                "confidence": round(max(0.2, 0.75 - depth * 0.15), 2),
            }

        # Neighbors: adjacent segments at shared intersections
        neighbor_segs = self.graph.get_neighboring_segments(origin_segment)
        for seg in neighbor_segs:
            if seg in affected:
                continue
            observed = self.current_congestion.get(seg, 0.0)
            estimated_congestion = origin_congestion * 0.4
            affected[seg] = {
                "segment_id": seg,
                "direction": "lateral",
                "hop_depth": 1,
                "estimated_congestion": round(estimated_congestion, 4),
                "observed_congestion": round(observed, 4),
                "severity": propagation_severity(estimated_congestion),
                "propagation_type": "intersection_spillover",
                "source": "network_inference",
                "confidence": 0.50,
            }

        # Enhance with ML predictions if available
        if predictions:
            for seg, seg_data in affected.items():
                if seg in predictions:
                    pred_congestion = predictions[seg].get("15m", {}).get("congestion", None)
                    if pred_congestion is not None:
                        seg_data["ml_predicted_congestion_15m"] = round(pred_congestion, 4)
                        seg_data["source"] = "network_inference+ml_prediction"

        # Filter to only truly affected segments (estimated > threshold)
        significant_affected = {
            seg: data for seg, data in affected.items()
            if data["estimated_congestion"] >= CONGESTION_THRESHOLD_MODERATE / 2
            or data["observed_congestion"] >= CONGESTION_THRESHOLD_MODERATE
        }

        # Build ordered list
        affected_list = sorted(
            significant_affected.values(),
            key=lambda x: (-x["estimated_congestion"], x["hop_depth"])
        )

        max_prop_depth = max((x["hop_depth"] for x in affected_list), default=0)

        # Overall confidence decreases with area
        overall_confidence = round(max(0.30, 0.85 - len(affected_list) * 0.02), 2)

        return {
            "origin_segment": origin_segment,
            "origin_congestion": round(origin_congestion, 4),
            "origin_severity": origin_severity,
            "affected_segments": affected_list,
            "total_affected": len(affected_list),
            "propagation_depth": max_prop_depth,
            "severity": origin_severity,
            "confidence": overall_confidence,
            "method": "network_inference",
            "disclaimer": (
                "Propagation estimates are based on network topology and "
                "observed correlation patterns. They are not causally validated. "
                "Use SUMO simulation for quantitative assessment."
            )
        }

    def get_affected_area_summary(self, origin_segment: str) -> dict:
        """Quick summary of affected segments by direction."""
        result = self.analyze(origin_segment)
        segs = result.get("affected_segments", [])
        return {
            "origin": origin_segment,
            "upstream_count": sum(1 for s in segs if s["direction"] == "upstream"),
            "downstream_count": sum(1 for s in segs if s["direction"] == "downstream"),
            "lateral_count": sum(1 for s in segs if s["direction"] == "lateral"),
            "total_affected": len(segs),
            "max_severity": max((s["severity"] for s in segs), key=lambda x: ["free","moderate","heavy","severe"].index(x), default="free"),
        }


def build_congestion_map(traffic_df: pd.DataFrame,
                          timestamp: Optional[pd.Timestamp] = None) -> Dict[str, float]:
    """
    Build segment_id → congestion_index mapping from the latest traffic state.
    """
    if timestamp is not None:
        df = traffic_df[traffic_df["timestamp"] == timestamp]
    else:
        df = traffic_df.loc[traffic_df.groupby("segment_id")["timestamp"].idxmax()]
    return dict(zip(df["segment_id"], df["congestion_index"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys
    sys.path.insert(0, r"d:\data-urban\traffic-intelligence")
    from backend.core.network_graph import get_network_graph
    from ml.preprocessing.data_loader import load_traffic

    g = get_network_graph()
    traffic = load_traffic("validation")
    cong_map = build_congestion_map(traffic)

    analyzer = CongestionPropagationAnalyzer(g, cong_map)

    # Find a congested segment to test
    top_seg = max(cong_map, key=cong_map.get)
    print(f"Testing propagation from most congested segment: {top_seg} (congestion={cong_map[top_seg]:.4f})")

    result = analyzer.analyze(top_seg, max_depth=3)
    print(f"Origin severity: {result['origin_severity']}")
    print(f"Affected segments: {result['total_affected']}")
    print(f"Propagation depth: {result['propagation_depth']}")
    print(f"Confidence: {result['confidence']}")
    for seg in result["affected_segments"][:5]:
        print(f"  {seg['segment_id']} ({seg['direction']}, depth={seg['hop_depth']}): "
              f"estimated={seg['estimated_congestion']:.4f}, observed={seg['observed_congestion']:.4f}")
