"""
Incident Impact Analysis
=========================
For each active incident, estimates its traffic impact:
  - affected capacity reduction
  - predicted congestion increase  
  - spatial extent (affected segments)
  - incident impact score

Does not claim exact causal relationships beyond what the data supports.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

INCIDENT_TYPE_BASE_IMPACT = {
    "road_closure": 0.9,
    "accident_like": 0.7,
    "lane_blockage": 0.55,
    "stalled_vehicle": 0.35,
    "demand_surge": 0.20,
}

SEVERITY_MULTIPLIER = {1: 0.6, 2: 1.0, 3: 1.5}


@dataclass
class IncidentImpact:
    incident_id: str
    segment_id: str
    incident_type: str
    severity: int
    lanes_blocked: int
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    # Computed fields
    capacity_reduction_pct: float = 0.0
    base_impact_score: float = 0.0
    current_congestion: float = 0.0
    predicted_congestion_increase: float = 0.0
    affected_segments: List[str] = field(default_factory=list)
    spatial_radius_hops: int = 0
    estimated_duration_min: Optional[float] = None
    overall_impact_score: float = 0.0
    confidence: float = 0.7


class IncidentAnalyzer:
    """
    Analyzes traffic incidents and estimates their network impact.
    """

    def __init__(self, network_graph, current_congestion: Optional[Dict[str, float]] = None):
        self.graph = network_graph
        self.current_congestion = current_congestion or {}

    def update_congestion(self, congestion_map: Dict[str, float]):
        self.current_congestion = congestion_map

    def analyze_incident(self,
                          incident: dict,
                          timestamp: Optional[pd.Timestamp] = None) -> IncidentImpact:
        """
        Analyze a single incident's traffic impact.

        Args:
            incident: dict with incident fields
            timestamp: current simulation time (for duration estimation)
        """
        seg_id = incident.get("segment_id", "")
        inc_type = incident.get("incident_type", "stalled_vehicle")
        severity = int(incident.get("severity", 1))
        lanes_blocked = int(incident.get("lanes_blocked", 0))

        seg_info = self.graph.get_segment_info(seg_id)
        total_lanes = seg_info.lanes if seg_info else 2
        capacity = seg_info.capacity_vph if seg_info else 1800

        # Capacity reduction
        if total_lanes > 0:
            lane_reduction_pct = min(0.9, lanes_blocked / total_lanes)
        else:
            lane_reduction_pct = 0.0

        base_impact = INCIDENT_TYPE_BASE_IMPACT.get(inc_type, 0.3)
        sev_mult = SEVERITY_MULTIPLIER.get(severity, 1.0)
        capacity_reduction_pct = min(0.95, lane_reduction_pct * 0.7 + base_impact * 0.3)

        current_congestion = self.current_congestion.get(seg_id, 0.0)
        predicted_increase = min(0.5, current_congestion * 0.5 + base_impact * sev_mult * 0.2)

        # Spatial extent: higher severity → larger radius
        spatial_radius = min(3, severity)
        affected_segs = []
        if seg_info:
            affected_segs = (
                self.graph.get_upstream_segments(seg_id, depth=spatial_radius) +
                self.graph.get_downstream_segments(seg_id, depth=1)
            )
            affected_segs = list(set(affected_segs))[:20]  # cap for performance

        # Duration estimation (if not already resolved)
        duration_min = None
        if timestamp is not None:
            end_time = incident.get("end_time")
            if pd.notna(end_time):
                end_ts = pd.Timestamp(end_time)
                if end_ts > timestamp:
                    duration_min = (end_ts - timestamp).total_seconds() / 60

        # Overall impact score (0–1)
        impact_score = min(1.0,
                           capacity_reduction_pct * 0.4 +
                           sev_mult * base_impact * 0.35 +
                           current_congestion * 0.25)

        return IncidentImpact(
            incident_id=incident.get("incident_id", ""),
            segment_id=seg_id,
            incident_type=inc_type,
            severity=severity,
            lanes_blocked=lanes_blocked,
            start_time=pd.Timestamp(incident.get("start_time")),
            end_time=pd.Timestamp(incident.get("end_time")),
            capacity_reduction_pct=round(capacity_reduction_pct, 3),
            base_impact_score=round(base_impact * sev_mult, 3),
            current_congestion=round(current_congestion, 4),
            predicted_congestion_increase=round(predicted_increase, 4),
            affected_segments=affected_segs,
            spatial_radius_hops=spatial_radius,
            estimated_duration_min=round(duration_min, 1) if duration_min is not None else None,
            overall_impact_score=round(impact_score, 3),
            confidence=0.65,
        )

    def get_active_incidents(self,
                              incidents_df: pd.DataFrame,
                              timestamp: pd.Timestamp) -> List[dict]:
        """Return incidents active at a given timestamp."""
        active = incidents_df[
            (incidents_df["start_time"] <= timestamp) &
            (incidents_df["end_time"] >= timestamp)
        ]
        return active.to_dict(orient="records")

    def analyze_all_active(self,
                            incidents_df: pd.DataFrame,
                            timestamp: pd.Timestamp) -> List[IncidentImpact]:
        """Analyze all active incidents at a timestamp."""
        active = self.get_active_incidents(incidents_df, timestamp)
        results = []
        for inc in active:
            impact = self.analyze_incident(inc, timestamp)
            results.append(impact)
        # Sort by impact score descending
        results.sort(key=lambda x: -x.overall_impact_score)
        return results

    def to_dict(self, impact: IncidentImpact) -> dict:
        return {
            "incident_id": impact.incident_id,
            "segment_id": impact.segment_id,
            "incident_type": impact.incident_type,
            "severity": impact.severity,
            "lanes_blocked": impact.lanes_blocked,
            "start_time": str(impact.start_time),
            "end_time": str(impact.end_time),
            "capacity_reduction_pct": impact.capacity_reduction_pct,
            "base_impact_score": impact.base_impact_score,
            "current_congestion": impact.current_congestion,
            "predicted_congestion_increase": impact.predicted_congestion_increase,
            "affected_segments": impact.affected_segments,
            "spatial_radius_hops": impact.spatial_radius_hops,
            "estimated_remaining_duration_min": impact.estimated_duration_min,
            "overall_impact_score": impact.overall_impact_score,
            "confidence": impact.confidence,
            "note": "Impact estimates based on capacity reduction + historical congestion patterns. Not causally validated."
        }
