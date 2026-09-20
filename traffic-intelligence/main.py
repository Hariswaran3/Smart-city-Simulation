"""
FastAPI Application — AI Traffic Intelligence System
====================================================
All endpoints documented with OpenAPI schemas.
"""

import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
MODELS_DIR = PROJECT_ROOT / "models"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Traffic Intelligence API",
    description="Urban Traffic Congestion Forecasting, Propagation Analysis, and Intervention Recommendation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount SUMO router
from backend.api.sumo_routes import router as sumo_router
app.include_router(sumo_router)


# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------

class AppState:
    initialized: bool = False
    network_graph = None
    features_train = None
    features_val = None
    targets_train = None
    targets_val = None
    feature_cols: List[str] = []
    predictor = None
    propagation_analyzer = None
    bottleneck_detector = None
    intervention_engine = None
    counterfactual_engine = None
    demand_analyzer = None
    incident_analyzer = None
    incidents_train = None
    incidents_val = None
    roadworks_train = None
    roadworks_val = None
    network_df = None
    od_demand = None
    planning_candidates = None
    latest_predictions = None
    congestion_map: Dict[str, float] = {}
    bottlenecks_cache: Optional[List[dict]] = None
    latest_timestamp: Optional[str] = None


state = AppState()


@app.on_event("startup")
async def startup_event():
    """Load all data and initialize intelligence modules on startup."""
    logger.info("Initializing AI Traffic Intelligence System …")
    try:
        await asyncio.get_event_loop().run_in_executor(None, _initialize_system)
        state.initialized = True
        logger.info("System initialized successfully.")
    except Exception as e:
        logger.error("Initialization failed: %s", e, exc_info=True)


def _initialize_system():
    """Synchronous initialization — runs in thread pool."""
    from ml.preprocessing.data_loader import (
        build_merged_dataset, load_incidents, load_roadworks,
        get_incident_active_flags, get_roadwork_active_flags,
        load_od_demand, load_network, load_planning_candidates
    )
    from ml.features.feature_engineering import run_full_feature_pipeline, get_feature_columns
    from backend.core.network_graph import get_network_graph
    from ml.predict import TrafficPredictor
    from backend.intelligence.congestion_propagation import CongestionPropagationAnalyzer, build_congestion_map
    from backend.intelligence.bottleneck_detection import BottleneckDetector
    from backend.intelligence.intervention_engine import InterventionEngine
    from backend.intelligence.counterfactual import CounterfactualEngine
    from backend.intelligence.demand_analysis import DemandAnalyzer
    from backend.intelligence.incident_analysis import IncidentAnalyzer

    logger.info("Loading network …")
    state.network_graph = get_network_graph()
    state.network_df = load_network()

    logger.info("Loading validation data (for live state) …")
    state.features_val, state.targets_val = build_merged_dataset("validation")
    # Keep last 2 days for fast live state serving
    cutoff = state.features_val["timestamp"].max() - pd.Timedelta(days=2)
    state.features_val = state.features_val[state.features_val["timestamp"] >= cutoff].copy()

    state.incidents_val = load_incidents("validation")
    state.roadworks_val = load_roadworks("validation")
    state.od_demand = load_od_demand()
    state.planning_candidates = load_planning_candidates()

    inc_flags = get_incident_active_flags(state.features_val, state.incidents_val)
    rw_flags = get_roadwork_active_flags(state.features_val, state.roadworks_val)

    logger.info("Running feature engineering on validation set …")
    state.features_val = run_full_feature_pipeline(
        state.features_val, inc_flags, rw_flags, state.od_demand, state.network_df
    )
    state.feature_cols = get_feature_columns(state.features_val)

    logger.info("Loading predictor …")
    state.predictor = TrafficPredictor(state.feature_cols)

    logger.info("Running batch predictions on latest traffic state …")
    latest_subset = state.features_val.loc[
        state.features_val.groupby("segment_id")["timestamp"].idxmax()
    ]
    state.latest_predictions = state.predictor.predict_batch(latest_subset)

    # Build congestion map from latest traffic observations
    state.congestion_map = build_congestion_map(state.features_val)
    state.latest_timestamp = str(state.features_val["timestamp"].max())

    logger.info("Initializing intelligence modules …")
    state.propagation_analyzer = CongestionPropagationAnalyzer(
        state.network_graph, state.congestion_map
    )
    state.bottleneck_detector = BottleneckDetector(state.network_graph)
    state.intervention_engine = InterventionEngine(
        state.network_graph, state.congestion_map
    )
    state.counterfactual_engine = CounterfactualEngine(
        state.network_graph, state.predictor
    )
    state.demand_analyzer = DemandAnalyzer(state.network_graph)
    state.incident_analyzer = IncidentAnalyzer(
        state.network_graph, state.congestion_map
    )

    logger.info("Pre-computing bottlenecks …")
    state.bottlenecks_cache = state.bottleneck_detector.get_top_bottlenecks(
        state.features_val, state.network_df, top_n=50
    )

    logger.info("Pre-generating SUMO scenario files …")
    try:
        from simulation.sumo.scenario_manager import get_scenario_manager
        get_scenario_manager()  # triggers scenario file generation
        logger.info("SUMO scenario manager ready.")
    except Exception as e:
        logger.warning("SUMO scenario pre-generation skipped: %s", e)

    logger.info("All systems ready. Latest timestamp: %s", state.latest_timestamp)


def _check_initialized():
    if not state.initialized:
        raise HTTPException(503, "System initializing, please retry in a few seconds.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """System health check."""
    model_count = 0
    registry_path = MODELS_DIR / "model_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            reg = json.load(f)
        model_count = len(reg.get("models", []))

    return {
        "status": "ready" if state.initialized else "initializing",
        "models_loaded": len(state.predictor.models) if state.predictor else 0,
        "model_registry_count": model_count,
        "network_segments": len(state.network_graph.segments) if state.network_graph else 0,
        "network_nodes": len(state.network_graph.nodes) if state.network_graph else 0,
        "data_loaded": state.initialized,
        "latest_timestamp": state.latest_timestamp,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/network")
async def get_network():
    """Return road network as GeoJSON FeatureCollection."""
    _check_initialized()
    return state.network_graph.to_geojson()


@app.get("/network/nodes")
async def get_nodes():
    """Return nodes as GeoJSON."""
    _check_initialized()
    return state.network_graph.to_nodes_geojson()


@app.get("/traffic/current")
async def get_current_traffic(limit: int = Query(default=436, le=500)):
    """Return current traffic state for all segments."""
    _check_initialized()
    latest = state.features_val.loc[
        state.features_val.groupby("segment_id")["timestamp"].idxmax()
    ]
    from ml.predict import classify_congestion, congestion_color
    result = []
    for _, row in latest.head(limit).iterrows():
        ci = float(row.get("congestion_index", 0))
        result.append({
            "segment_id": row["segment_id"],
            "timestamp": str(row["timestamp"]),
            "speed_kmh": float(row.get("speed_kmh", 0)),
            "flow_vph": float(row.get("flow_vph", 0)),
            "occupancy_pct": float(row.get("occupancy_pct", 0)),
            "congestion_index": ci,
            "congestion_level": classify_congestion(ci),
            "color": congestion_color(ci),
            "delay_min": float(row.get("delay_min", 0)),
            "queue_length_veh": float(row.get("queue_length_veh", 0)),
        })
    return {"timestamp": state.latest_timestamp, "segments": result}


@app.get("/traffic/forecast")
async def get_traffic_forecast(
    horizon: str = Query(default="15m", description="Forecast horizon: 15m, 30m, 45m, 60m"),
    limit: int = Query(default=436, le=500)
):
    """Return forecast congestion map for a given horizon."""
    _check_initialized()
    if state.latest_predictions is None:
        raise HTTPException(503, "Predictions not yet computed.")

    # Get latest predictions per segment
    preds = state.latest_predictions.loc[
        state.latest_predictions.groupby("segment_id")["timestamp"].idxmax()
    ]

    from ml.predict import classify_congestion, congestion_color
    result = []
    col_cong = f"pred_congestion_{horizon}"
    col_speed = f"pred_speed_{horizon}"
    col_flow = f"pred_flow_{horizon}"

    for _, row in preds.head(limit).iterrows():
        ci = float(row.get(col_cong, 0)) if col_cong in preds.columns else 0.0
        result.append({
            "segment_id": row["segment_id"],
            "horizon": horizon,
            "congestion_index": ci,
            "congestion_level": classify_congestion(ci),
            "color": congestion_color(ci),
            "speed_kmh": float(row.get(col_speed, 0)) if col_speed in preds.columns else None,
            "flow_vph": float(row.get(col_flow, 0)) if col_flow in preds.columns else None,
        })
    return {"horizon": horizon, "timestamp": state.latest_timestamp, "segments": result}


@app.get("/traffic/segment/{segment_id}")
async def get_segment_detail(segment_id: str):
    """Return detailed traffic state + multi-horizon forecast for a segment."""
    _check_initialized()
    seg_features = state.features_val[state.features_val["segment_id"] == segment_id]
    if seg_features.empty:
        raise HTTPException(404, f"Segment {segment_id} not found")

    latest_row = seg_features.loc[seg_features["timestamp"].idxmax()]
    seg_info = state.network_graph.get_segment_info(segment_id)

    from ml.predict import classify_congestion, congestion_color
    ci = float(latest_row.get("congestion_index", 0))

    # Multi-horizon forecast
    latest_df = seg_features.loc[[seg_features["timestamp"].idxmax()]]
    forecast = state.predictor.predict_segment(segment_id, latest_df)

    # Propagation
    propagation = state.propagation_analyzer.analyze(segment_id, max_depth=2)

    # Bottleneck info
    bottleneck_entry = next(
        (b for b in (state.bottlenecks_cache or []) if b["segment_id"] == segment_id),
        None
    )

    # Incidents
    import pandas as pd
    ts = pd.Timestamp(latest_row["timestamp"])
    active_incidents = state.incident_analyzer.get_active_incidents(state.incidents_val, ts)
    seg_incidents = [i for i in active_incidents if i.get("segment_id") == segment_id]

    # Interventions
    interventions = state.intervention_engine.get_interventions_for_segment(
        segment_id, state.planning_candidates,
        forecast_congestion={segment_id: float(forecast["horizons"].get("+15m", {}).get("congestion", ci))}
    )

    return {
        "segment_id": segment_id,
        "current_state": {
            "timestamp": str(latest_row["timestamp"]),
            "speed_kmh": float(latest_row.get("speed_kmh", 0)),
            "flow_vph": float(latest_row.get("flow_vph", 0)),
            "occupancy_pct": float(latest_row.get("occupancy_pct", 0)),
            "congestion_index": ci,
            "congestion_level": classify_congestion(ci),
            "color": congestion_color(ci),
            "delay_min": float(latest_row.get("delay_min", 0)),
            "queue_length_veh": float(latest_row.get("queue_length_veh", 0)),
        },
        "network": {
            "road_class": seg_info.road_class if seg_info else "",
            "lanes": seg_info.lanes if seg_info else 0,
            "capacity_vph": seg_info.capacity_vph if seg_info else 0,
            "free_flow_speed_kmh": seg_info.free_flow_speed_kmh if seg_info else 0,
            "length_km": seg_info.length_km if seg_info else 0,
            "structural_bottleneck": seg_info.structural_bottleneck if seg_info else 0,
            "importance": seg_info.importance if seg_info else 0,
        },
        "coordinates": state.network_graph.get_segment_coords(segment_id),
        "forecast": forecast["horizons"],
        "explanation": forecast.get("explanation", {}),
        "propagation_summary": {
            "total_affected": propagation.get("total_affected", 0),
            "propagation_depth": propagation.get("propagation_depth", 0),
            "method": propagation.get("method", ""),
        },
        "bottleneck": bottleneck_entry,
        "active_incidents": seg_incidents,
        "candidate_interventions": interventions[:3],
    }


@app.get("/congestion/map")
async def get_congestion_map(
    horizon: str = Query(default="15m"),
    min_congestion: float = Query(default=0.0)
):
    """Return full congestion map for a given forecast horizon."""
    _check_initialized()
    congestion_data = await get_traffic_forecast(horizon=horizon, limit=500)
    segments = congestion_data["segments"]
    if min_congestion > 0:
        segments = [s for s in segments if s["congestion_index"] >= min_congestion]
    return {"horizon": horizon, "timestamp": state.latest_timestamp, "segments": segments}


@app.get("/incidents")
async def get_incidents(active_only: bool = Query(default=True)):
    """Return incidents with impact analysis."""
    _check_initialized()
    import pandas as pd
    ts = pd.Timestamp(state.latest_timestamp)

    if active_only:
        active = state.incident_analyzer.get_active_incidents(state.incidents_val, ts)
    else:
        active = state.incidents_val.to_dict(orient="records")

    results = []
    for inc in active:
        impact = state.incident_analyzer.analyze_incident(inc, ts)
        results.append(state.incident_analyzer.to_dict(impact))
    return {"timestamp": str(ts), "incidents": results, "count": len(results)}


@app.get("/roadworks")
async def get_roadworks(active_only: bool = Query(default=True)):
    """Return roadworks."""
    _check_initialized()
    import pandas as pd
    ts = pd.Timestamp(state.latest_timestamp)
    if active_only:
        df = state.roadworks_val
        active = df[
            (df["start_time"] <= ts) &
            (df["end_time"] >= ts)
        ].to_dict(orient="records")
    else:
        active = state.roadworks_val.to_dict(orient="records")
    return {"timestamp": str(ts), "roadworks": active, "count": len(active)}


@app.get("/bottlenecks")
async def get_bottlenecks(top_n: int = Query(default=20, le=100)):
    """Return top bottleneck segments."""
    _check_initialized()
    result = (state.bottlenecks_cache or [])[:top_n]
    return {"bottlenecks": result, "count": len(result)}


@app.get("/propagation/{segment_id}")
async def get_propagation(
    segment_id: str,
    max_depth: int = Query(default=3, le=5)
):
    """Return congestion propagation analysis for a segment."""
    _check_initialized()
    if segment_id not in state.network_graph.segments:
        raise HTTPException(404, f"Segment {segment_id} not found")

    result = state.propagation_analyzer.analyze(segment_id, max_depth=max_depth)
    return result


@app.get("/interventions")
async def get_interventions(top_n: int = Query(default=20, le=90)):
    """Return top ranked intervention candidates."""
    _check_initialized()
    # Use 15min forecast congestion for scoring
    forecast_cong = {}
    if state.latest_predictions is not None:
        preds = state.latest_predictions.loc[
            state.latest_predictions.groupby("segment_id")["timestamp"].idxmax()
        ]
        col = "pred_congestion_15m"
        if col in preds.columns:
            forecast_cong = dict(zip(preds["segment_id"], preds[col]))

    ranked = state.intervention_engine.rank_candidates(
        state.planning_candidates, forecast_cong, state.network_df, top_n=top_n
    )
    return {"interventions": ranked, "count": len(ranked)}


@app.post("/counterfactual")
async def run_counterfactual(request: dict):
    """
    Run counterfactual analysis: what-if an intervention is applied.
    Request body: {segment_id, intervention_type, capacity_delta_vph, horizon}
    """
    _check_initialized()
    segment_id = request.get("segment_id", "")
    if segment_id not in state.network_graph.segments:
        raise HTTPException(404, f"Segment {segment_id} not found")

    latest_features = state.features_val.loc[
        state.features_val.groupby("segment_id")["timestamp"].idxmax()
    ]

    result = state.counterfactual_engine.run_scenario(
        segment_id=segment_id,
        intervention={
            "intervention_type": request.get("intervention_type", "capacity_upgrade"),
            "capacity_delta_vph": float(request.get("capacity_delta_vph", 500)),
        },
        current_features=latest_features,
        horizon=request.get("horizon", "30m"),
    )
    return result


@app.post("/simulation/sumo")
async def run_sumo_legacy(request: dict):
    """Deprecated — use POST /sumo/run instead."""
    return {
        "deprecated": True,
        "message": "Use POST /sumo/run with {network, demand, disruption} body. See /docs.",
        "new_endpoint": "/sumo/run",
    }



@app.get("/model/metrics")
async def get_model_metrics():
    """Return model evaluation metrics from registry."""
    registry_path = MODELS_DIR / "model_registry.json"
    if not registry_path.exists():
        raise HTTPException(404, "Model registry not found. Run training first.")
    with open(registry_path) as f:
        registry = json.load(f)

    eval_path = PROJECT_ROOT / "reports" / "evaluation_results.json"
    evaluation = {}
    if eval_path.exists():
        with open(eval_path) as f:
            evaluation = json.load(f)

    return {"registry": registry, "evaluation": evaluation}


@app.get("/model/explain/{segment_id}")
async def explain_segment(segment_id: str):
    """Return feature importance explanation for a segment's forecast."""
    _check_initialized()
    seg_features = state.features_val[state.features_val["segment_id"] == segment_id]
    if seg_features.empty:
        raise HTTPException(404, f"Segment {segment_id} not found")

    latest = seg_features.loc[[seg_features["timestamp"].idxmax()]]
    result = state.predictor.predict_segment(segment_id, latest)
    return {
        "segment_id": segment_id,
        "explanation": result.get("explanation", {}),
        "note": "Feature contributions are approximations using feature_importance × feature_magnitude. Not SHAP-verified.",
    }


@app.get("/demand")
async def get_demand_summary():
    """Return OD demand summary and high-demand corridors."""
    _check_initialized()
    summary = state.demand_analyzer.get_demand_summary(state.od_demand)
    corridors = state.demand_analyzer.get_high_demand_corridors(state.od_demand, top_n=10)
    return {"summary": summary, "top_corridors": corridors}


# ---- Frontend serving ----

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def serve_dashboard():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8050, reload=False)
