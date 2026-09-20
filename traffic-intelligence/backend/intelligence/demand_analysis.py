"""
OD Demand Intelligence
========================
Analyzes Origin-Destination demand profiles to identify
high-demand corridors, demand pressure, and overloaded paths.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DemandAnalyzer:
    """
    Analyzes OD demand profiles and connects them to network congestion.
    Does not claim exact vehicle routing — only demand pressure inference.
    """

    def __init__(self, network_graph=None):
        self.graph = network_graph

    def compute_node_demand_pressure(self, od_demand: pd.DataFrame) -> pd.DataFrame:
        """
        Compute demand pressure at each node.
        Origin demand = total vph departing from node.
        Destination demand = total vph arriving at node.
        """
        origin_pressure = od_demand.groupby("origin_node")["base_demand_vph"].agg(
            total_origin_demand="sum",
            od_pair_count="count"
        ).reset_index().rename(columns={"origin_node": "node_id"})

        dest_pressure = od_demand.groupby("destination_node")["base_demand_vph"].agg(
            total_dest_demand="sum"
        ).reset_index().rename(columns={"destination_node": "node_id"})

        node_demand = origin_pressure.merge(dest_pressure, on="node_id", how="outer").fillna(0)
        node_demand["total_node_demand"] = (
            node_demand["total_origin_demand"] + node_demand["total_dest_demand"]
        )
        return node_demand.sort_values("total_node_demand", ascending=False)

    def compute_segment_demand_pressure(self,
                                          od_demand: pd.DataFrame,
                                          network_df: pd.DataFrame) -> pd.DataFrame:
        """
        Estimate demand pressure per segment based on endpoint node demand.
        """
        node_demand = self.compute_node_demand_pressure(od_demand)
        node_demand_map = dict(zip(node_demand["node_id"], node_demand["total_node_demand"]))

        result = network_df[["segment_id", "source_node", "target_node", "capacity_vph"]].copy()
        result["source_demand"] = result["source_node"].map(node_demand_map).fillna(0)
        result["target_demand"] = result["target_node"].map(node_demand_map).fillna(0)
        result["segment_demand_pressure"] = (
            result["source_demand"] * 0.6 + result["target_demand"] * 0.4
        )
        # Demand pressure ratio (relative to capacity)
        cap = result["capacity_vph"].replace(0, np.nan)
        result["demand_capacity_ratio"] = (result["segment_demand_pressure"] / cap / 3).clip(0, 2)
        return result.sort_values("segment_demand_pressure", ascending=False)

    def get_high_demand_corridors(self,
                                    od_demand: pd.DataFrame,
                                    top_n: int = 20) -> List[dict]:
        """Return top OD pairs by demand."""
        top = od_demand.nlargest(top_n, "base_demand_vph")
        return top.to_dict(orient="records")

    def get_demand_summary(self, od_demand: pd.DataFrame) -> dict:
        """Summary statistics for OD demand."""
        purposes = od_demand.groupby("purpose")["base_demand_vph"].agg(
            count="count", total="sum", mean="mean"
        ).to_dict(orient="index")

        return {
            "total_od_pairs": len(od_demand),
            "total_base_demand_vph": float(od_demand["base_demand_vph"].sum()),
            "mean_demand_per_pair": float(od_demand["base_demand_vph"].mean()),
            "max_demand_pair": float(od_demand["base_demand_vph"].max()),
            "by_purpose": purposes,
            "unique_origins": od_demand["origin_node"].nunique(),
            "unique_destinations": od_demand["destination_node"].nunique(),
            "note": "Demand pressure inferences are based on node-level aggregation, not vehicle-level routing."
        }
