"""
Pydantic Schemas for the Traffic Intelligence API
==================================================
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---- Network ----

class SegmentProperties(BaseModel):
    segment_id: str
    source_node: str
    target_node: str
    road_class: str
    lanes: int
    capacity_vph: float
    free_flow_speed_kmh: float
    length_km: float
    structural_bottleneck: int
    importance: float


class NodeProperties(BaseModel):
    node_id: str
    lat: float
    lon: float


# ---- Traffic ----

class TrafficState(BaseModel):
    segment_id: str
    timestamp: str
    speed_kmh: float
    flow_vph: float
    occupancy_pct: Optional[float]
    congestion_index: float
    congestion_level: str
    delay_min: Optional[float]
    queue_length_veh: Optional[float]
    sensor_quality: Optional[float]


# ---- Forecasting ----

class HorizonForecast(BaseModel):
    horizon: str
    speed: Optional[float]
    flow: Optional[float]
    congestion: Optional[float]
    congestion_level: Optional[str]
    color: Optional[str]
    model_type: Optional[str]
    confidence: Optional[float]


class SegmentForecast(BaseModel):
    segment_id: str
    horizons: Dict[str, HorizonForecast]
    explanation: Optional[Dict[str, Any]]


# ---- Congestion Map ----

class CongestionMapEntry(BaseModel):
    segment_id: str
    congestion_index: float
    congestion_level: str
    color: str
    horizon: str
    speed_kmh: Optional[float]
    flow_vph: Optional[float]


# ---- Incidents ----

class IncidentRecord(BaseModel):
    incident_id: str
    segment_id: str
    incident_type: str
    severity: int
    lanes_blocked: int
    start_time: str
    end_time: str
    capacity_reduction_pct: Optional[float]
    overall_impact_score: Optional[float]
    affected_segments: Optional[List[str]]
    confidence: Optional[float]


# ---- Roadworks ----

class RoadworkRecord(BaseModel):
    work_id: str
    segment_id: str
    start_time: str
    end_time: str
    closure_fraction: float
    work_type: str


# ---- Bottlenecks ----

class BottleneckFactor(BaseModel):
    congestion_frequency: float
    capacity_utilization: float
    queue_pressure: float
    structural_flag: float
    network_importance: float
    upstream_pressure: float
    severity_weight: float


class BottleneckRecord(BaseModel):
    segment_id: str
    bottleneck_score: float
    bottleneck_class: str
    factors: BottleneckFactor
    reason: List[str]
    confidence: float


# ---- Propagation ----

class PropagationSegment(BaseModel):
    segment_id: str
    direction: str
    hop_depth: int
    estimated_congestion: float
    observed_congestion: float
    severity: str
    propagation_type: str
    source: str
    confidence: float


class PropagationResult(BaseModel):
    origin_segment: str
    origin_congestion: float
    origin_severity: str
    affected_segments: List[PropagationSegment]
    total_affected: int
    propagation_depth: int
    severity: str
    confidence: float
    method: str
    disclaimer: str


# ---- Interventions ----

class InterventionCandidate(BaseModel):
    candidate_id: str
    segment_id: str
    intervention_type: str
    feasibility_band: str
    capacity_delta_vph: float
    cost_index: float
    current_congestion: float
    forecast_congestion_15m: float
    predicted_congestion_reduction: float
    estimated_benefit_score: float
    priority_score: float
    affected_network: List[str]
    confidence: float
    disclaimer: str


# ---- Counterfactual ----

class CounterfactualRequest(BaseModel):
    segment_id: str
    horizon: str = "30m"
    intervention_type: str
    capacity_delta_vph: float = 0.0
    timestamp: Optional[str] = None


class CounterfactualResult(BaseModel):
    segment_id: str
    horizon: str
    intervention: Dict[str, Any]
    baseline: Dict[str, Any]
    intervention_scenario: Dict[str, Any]
    delta: Dict[str, Any]
    affected_segments: List[str]
    source: str
    confidence: float
    disclaimer: str


# ---- Model metrics ----

class ModelMetrics(BaseModel):
    model_key: str
    target_type: str
    horizon: str
    metrics: Dict[str, Any]
    top_features: Dict[str, float]
    training_timestamp: str


# ---- Health ----

class HealthResponse(BaseModel):
    status: str
    models_loaded: int
    network_segments: int
    network_nodes: int
    data_loaded: bool
    timestamp: str
