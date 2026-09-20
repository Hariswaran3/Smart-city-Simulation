"""
Bottleneck Detection
=====================
Detects recurring and dynamic bottlenecks across the road network.
Considers: congestion frequency, capacity utilization, queue pressure,
           road importance, structural flags, and network pressure.

Returns per-segment bottleneck scores with decomposed contributing factors.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class BottleneckDetector:
    """
    Identifies segments that are persistent or dynamic bottlenecks.
    
    Score factors (all 0–1):
      1. congestion_frequency   — fraction of time steps with elevated congestion
      2. capacity_utilization   — mean flow / capacity
      3. queue_pressure         — mean queue_length relative to capacity
      4. structural_flag        — pre-flagged structural bottleneck
      5. network_importance     — PageRank or importance score
      6. upstream_pressure      — congestion propagating from upstream
      7. severity_weight        — proportion of severe vs moderate congestion
    """

    WEIGHTS = {
        "congestion_frequency": 0.25,
        "capacity_utilization": 0.20,
        "queue_pressure": 0.15,
        "structural_flag": 0.10,
        "network_importance": 0.10,
        "upstream_pressure": 0.10,
        "severity_weight": 0.10,
    }

    CONGESTION_THRESHOLD = 0.10

    def __init__(self, network_graph=None):
        self.graph = network_graph

    def compute_segment_stats(self,
                               traffic_df: pd.DataFrame,
                               network_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute per-segment statistics needed for bottleneck scoring.
        Returns a DataFrame indexed by segment_id.
        """
        # Group by segment
        grp = traffic_df.groupby("segment_id")

        stats = pd.DataFrame({
            "mean_congestion": grp["congestion_index"].mean(),
            "max_congestion": grp["congestion_index"].max(),
            "congestion_freq": grp["congestion_index"].apply(
                lambda x: (x >= self.CONGESTION_THRESHOLD).mean()
            ),
            "severity_freq": grp["congestion_index"].apply(
                lambda x: (x >= 0.30).mean()
            ),
            "mean_flow": grp["flow_vph"].mean(),
            "mean_queue": grp["queue_length_veh"].mean() if "queue_length_veh" in traffic_df.columns else 0,
            "mean_delay": grp["delay_min"].mean() if "delay_min" in traffic_df.columns else 0,
        })

        # Merge network attributes
        net_cols = ["segment_id", "capacity_vph", "lanes", "importance",
                    "structural_bottleneck", "road_class", "length_km"]
        net_sub = network_df[[c for c in net_cols if c in network_df.columns]].set_index("segment_id")
        stats = stats.join(net_sub, how="left")

        # Compute capacity utilization
        cap = stats["capacity_vph"].replace(0, np.nan)
        stats["capacity_utilization"] = (stats["mean_flow"] / cap).clip(0, 1.5)

        # Queue pressure (normalized by segment length as proxy)
        stats["queue_pressure"] = (stats["mean_queue"] / 50.0).clip(0, 1.0)

        return stats

    def score_bottlenecks(self,
                           stats: pd.DataFrame,
                           upstream_congestion: Optional[Dict[str, float]] = None) -> pd.DataFrame:
        """
        Compute bottleneck scores for all segments.
        Returns DataFrame with score columns and sorted by total score.
        """
        df = stats.copy()

        # Normalize each factor to [0, 1]
        df["f_congestion_frequency"] = df["congestion_freq"].clip(0, 1)
        df["f_capacity_utilization"] = df["capacity_utilization"].clip(0, 1)
        df["f_queue_pressure"] = df["queue_pressure"].clip(0, 1)
        df["f_structural_flag"] = df.get("structural_bottleneck", 0).fillna(0).clip(0, 1)
        df["f_network_importance"] = df.get("importance", 0.5).fillna(0.5).clip(0, 1)
        df["f_severity_weight"] = df["severity_freq"].clip(0, 1)

        if upstream_congestion:
            df["f_upstream_pressure"] = df.index.map(
                lambda seg: upstream_congestion.get(seg, 0.0)
            ).clip(0, 1)
        else:
            df["f_upstream_pressure"] = df["f_congestion_frequency"] * 0.5

        # Weighted sum
        df["bottleneck_score"] = sum(
            self.WEIGHTS[factor] * df[f"f_{factor}"]
            for factor in self.WEIGHTS
        )
        df["bottleneck_score"] = df["bottleneck_score"].clip(0, 1).round(4)

        # Classify
        df["bottleneck_class"] = pd.cut(
            df["bottleneck_score"],
            bins=[0, 0.2, 0.4, 0.6, 0.8, 1.01],
            labels=["minimal", "low", "moderate", "high", "critical"],
            right=False
        )

        return df.sort_values("bottleneck_score", ascending=False)

    def get_top_bottlenecks(self,
                             traffic_df: pd.DataFrame,
                             network_df: pd.DataFrame,
                             top_n: int = 20) -> List[dict]:
        """
        Return the top-N bottlenecks as a list of dicts.
        Each dict includes decomposed factor scores and reasoning.
        """
        stats = self.compute_segment_stats(traffic_df, network_df)
        scored = self.score_bottlenecks(stats)

        results = []
        for seg_id, row in scored.head(top_n).iterrows():
            reasons = self._build_reasons(row)
            entry = {
                "segment_id": seg_id,
                "bottleneck_score": float(row["bottleneck_score"]),
                "bottleneck_class": str(row.get("bottleneck_class", "unknown")),
                "factors": {
                    "congestion_frequency": float(row.get("f_congestion_frequency", 0)),
                    "capacity_utilization": float(row.get("f_capacity_utilization", 0)),
                    "queue_pressure": float(row.get("f_queue_pressure", 0)),
                    "structural_flag": float(row.get("f_structural_flag", 0)),
                    "network_importance": float(row.get("f_network_importance", 0)),
                    "upstream_pressure": float(row.get("f_upstream_pressure", 0)),
                    "severity_weight": float(row.get("f_severity_weight", 0)),
                },
                "stats": {
                    "mean_congestion": float(row.get("mean_congestion", 0)),
                    "max_congestion": float(row.get("max_congestion", 0)),
                    "mean_capacity_utilization": float(row.get("capacity_utilization", 0)),
                    "mean_queue_length": float(row.get("mean_queue", 0)),
                    "road_class": str(row.get("road_class", "")),
                    "lanes": int(row.get("lanes", 0)) if pd.notna(row.get("lanes")) else 0,
                    "structural_bottleneck": bool(row.get("structural_bottleneck", 0)),
                },
                "reason": reasons,
                "confidence": self._confidence_from_score(float(row["bottleneck_score"])),
            }
            results.append(entry)
        return results

    def _build_reasons(self, row: pd.Series) -> List[str]:
        """Generate human-readable reasons for bottleneck classification."""
        reasons = []
        if row.get("f_congestion_frequency", 0) > 0.3:
            reasons.append(f"High congestion frequency ({row.get('congestion_freq', 0):.1%} of time steps)")
        if row.get("f_capacity_utilization", 0) > 0.6:
            reasons.append(f"High capacity utilization ({row.get('capacity_utilization', 0):.1%})")
        if row.get("f_structural_flag", 0) > 0:
            reasons.append("Pre-identified structural bottleneck in network data")
        if row.get("f_queue_pressure", 0) > 0.3:
            reasons.append(f"Elevated queue pressure (mean queue: {row.get('mean_queue', 0):.1f} vehicles)")
        if row.get("f_severity_weight", 0) > 0.1:
            reasons.append(f"Frequent severe congestion ({row.get('severity_freq', 0):.1%} of time at severe level)")
        if row.get("f_network_importance", 0) > 0.7:
            reasons.append("High network importance / centrality")
        if not reasons:
            reasons.append("Moderate congestion across multiple indicators")
        return reasons

    def _confidence_from_score(self, score: float) -> float:
        """Confidence scales with bottleneck score — stronger evidence → higher confidence."""
        return round(min(0.95, 0.4 + score * 0.6), 2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys
    sys.path.insert(0, r"d:\data-urban\traffic-intelligence")
    from ml.preprocessing.data_loader import load_traffic, load_network
    from backend.core.network_graph import get_network_graph
    import json

    traffic = load_traffic("train")
    network = load_network()
    g = get_network_graph()

    detector = BottleneckDetector(g)
    top = detector.get_top_bottlenecks(traffic, network, top_n=10)

    print("Top 10 Bottlenecks:")
    for b in top:
        print(f"  {b['segment_id']}: score={b['bottleneck_score']:.3f}, "
              f"class={b['bottleneck_class']}, reasons={b['reason'][:1]}")
    print("Done.")
