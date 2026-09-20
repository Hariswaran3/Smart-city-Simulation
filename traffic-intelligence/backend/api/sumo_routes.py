"""
SUMO API Router
================
Clean REST endpoints for SUMO scenario management and simulation runs.

GET  /sumo/scenarios              — list available scenarios
POST /sumo/run                    — submit a run (returns run_id immediately)
GET  /sumo/status/{run_id}        — poll run status
GET  /sumo/results/{run_id}       — fetch completed results
GET  /sumo/engine                 — SUMO engine availability
POST /sumo/counterfactual         — baseline vs intervention comparison
"""

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sumo", tags=["SUMO Simulation"])


def _get_manager():
    from simulation.sumo.scenario_manager import get_scenario_manager
    return get_scenario_manager()


# ----- Request / Response schemas -----

class RunRequest(BaseModel):
    network: str = "four_way"           # four_way | one_way | two_way | t_junction
    demand: str = "normal"              # normal | peak | directional_peak | surge
    disruption: str = "none"           # none | accident | roadwork | lane_block
    intervention: Optional[dict] = None
    demand_scale: Optional[float] = None


class CounterfactualRequest(BaseModel):
    network: str = "t_junction"
    demand: str = "peak"
    disruption: str = "accident"
    intervention: dict = {"type": "signal_optimization", "description": "Extend green for main road by 15s"}


# ----- Endpoints -----

@router.get("/engine")
async def get_engine_status():
    """Return SUMO engine availability."""
    try:
        mgr = _get_manager()
        return {
            "sumo_available": mgr.sumo_available,
            "status": "AVAILABLE" if mgr.sumo_available else "NOT_AVAILABLE",
            "message": (
                "Real SUMO simulation active." if mgr.sumo_available
                else "SUMO not detected. Using mock simulator. Install SUMO and set SUMO_HOME to enable real simulation."
            )
        }
    except Exception as e:
        logger.error("Engine status error: %s", e)
        return {"sumo_available": False, "status": "ERROR", "message": str(e)}


@router.get("/scenarios")
async def list_scenarios():
    """List available scenario types."""
    mgr = _get_manager()
    return {"scenarios": mgr.list_scenarios()}


@router.post("/run")
async def submit_run(req: RunRequest):
    """
    Submit a new simulation run. Returns run_id immediately.
    Poll /sumo/status/{run_id} for completion.
    """
    valid_networks = ["four_way", "one_way", "two_way", "t_junction"]
    valid_demands = ["normal", "peak", "directional_peak", "surge"]
    valid_disruptions = ["none", "accident", "roadwork", "lane_block"]

    if req.network not in valid_networks:
        raise HTTPException(400, f"Unknown network: {req.network}. Valid: {valid_networks}")
    if req.demand not in valid_demands:
        raise HTTPException(400, f"Unknown demand: {req.demand}. Valid: {valid_demands}")
    if req.disruption not in valid_disruptions:
        raise HTTPException(400, f"Unknown disruption: {req.disruption}. Valid: {valid_disruptions}")

    try:
        mgr = _get_manager()
        run_id = mgr.submit_run(
            scenario_type=req.network,
            demand=req.demand,
            disruption=req.disruption,
            intervention=req.intervention,
            demand_scale=req.demand_scale,
        )
        logger.info("Run submitted: %s (network=%s, demand=%s, disruption=%s)", run_id, req.network, req.demand, req.disruption)

        # Wait a short time to catch immediately available mock results
        await asyncio.sleep(0.3)
        record = mgr.get_run(run_id)
        if record and record.status == "COMPLETED":
            return {**mgr.get_run_results(run_id)["metrics"], "run_id": run_id, "status": "COMPLETED"}

        return {
            "run_id": run_id,
            "status": "RUNNING",
            "message": f"Simulation submitted. Poll /sumo/status/{run_id} for updates.",
        }
    except Exception as e:
        logger.error("Run submission failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Failed to submit run: {e}")


@router.get("/status/{run_id}")
async def get_run_status(run_id: str):
    """Poll simulation status: QUEUED | RUNNING | COMPLETED | FAILED."""
    mgr = _get_manager()
    result = mgr.get_run_status(run_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/results/{run_id}")
async def get_run_results(run_id: str):
    """Return full simulation metrics for a completed run."""
    mgr = _get_manager()
    result = mgr.get_run_results(run_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    if result["status"] != "COMPLETED":
        return result
    return result


@router.post("/counterfactual")
async def run_counterfactual(req: CounterfactualRequest):
    """
    Run baseline and intervention scenarios and compare.
    Runs both sequentially; for real SUMO, expects ~30-120s per run.
    """
    mgr = _get_manager()

    # Submit baseline
    baseline_id = mgr.submit_run(
        scenario_type=req.network,
        demand=req.demand,
        disruption=req.disruption,
        intervention=None,
    )
    # Submit intervention
    intervention_id = mgr.submit_run(
        scenario_type=req.network,
        demand=req.demand,
        disruption=req.disruption,
        intervention=req.intervention,
    )

    # Wait for both (mock completes instantly; real SUMO may take longer)
    for _ in range(120):  # max 120 × 0.5s = 60s
        await asyncio.sleep(0.5)
        b_rec = mgr.get_run(baseline_id)
        i_rec = mgr.get_run(intervention_id)
        if b_rec and i_rec:
            if b_rec.status in ("COMPLETED", "FAILED") and i_rec.status in ("COMPLETED", "FAILED"):
                break

    b_res = mgr.get_run_results(baseline_id)
    i_res = mgr.get_run_results(intervention_id)

    bm = b_res.get("metrics") or {}
    im = i_res.get("metrics") or {}

    def delta(key):
        bv = bm.get(key, 0) or 0
        iv = im.get(key, 0) or 0
        return round(iv - bv, 3)

    def pct_change(key):
        bv = bm.get(key, 0) or 0
        iv = im.get(key, 0) or 0
        if bv == 0:
            return None
        return round((iv - bv) / bv * 100, 1)

    return {
        "baseline_run_id": baseline_id,
        "intervention_run_id": intervention_id,
        "scenario_type": req.network,
        "demand": req.demand,
        "disruption": req.disruption,
        "intervention": req.intervention,
        "baseline": bm,
        "intervention_scenario": im,
        "delta": {
            "mean_travel_time_s": delta("mean_travel_time_s"),
            "mean_speed_kmh": delta("mean_speed_kmh"),
            "mean_throughput_vph": delta("mean_throughput_vph"),
            "mean_queue_length_veh": delta("mean_queue_length_veh"),
            "total_delay_veh_h": delta("total_delay_veh_h"),
        },
        "pct_change": {
            "travel_time": pct_change("mean_travel_time_s"),
            "speed": pct_change("mean_speed_kmh"),
            "throughput": pct_change("mean_throughput_vph"),
            "queue": pct_change("mean_queue_length_veh"),
            "delay": pct_change("total_delay_veh_h"),
        },
        "source": bm.get("source", "unknown"),
        "disclaimer": bm.get("disclaimer", ""),
    }
@router.get("/stream")
def sumo_stream():
    from fastapi.responses import StreamingResponse
    import time
    from simulation.sumo import simulator
    
    def generate():
        while True:
            frame = simulator.SUMO_STREAM_FRAME
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.1)
            
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
