"""
SUMO Scenario Manager
======================
Manages lifecycle of SUMO simulation runs:
  - Generates / locates scenario files
  - Runs simulations asynchronously in thread pool
  - Stores results keyed by run_id
  - Supports demand scaling, disruption injection, and intervention application

Source labels:
  'sumo_simulation'  — real SUMO via TraCI
  'mock_simulator'   — mock fallback (SUMO not installed)
"""

import uuid
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from simulation.sumo.scenarios.generator import ScenarioGenerator, get_scenario_path, DEMAND_PROFILES, DISRUPTION_CAPACITY_FACTORS
from simulation.sumo.simulator import SUMOSimulator, MockSimulator, SimulationScenario, SimulationMetrics, get_simulator

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCENARIOS_DIR = Path(__file__).parent / "scenarios"


@dataclass
class RunRecord:
    run_id: str
    scenario_type: str
    demand: str
    disruption: str
    intervention: Optional[dict]
    status: str          # QUEUED | RUNNING | COMPLETED | FAILED
    created_at: float
    completed_at: Optional[float] = None
    metrics: Optional[dict] = None
    error: Optional[str] = None


class ScenarioManager:
    """
    Manages SUMO simulation runs asynchronously.
    Thread-safe run registry.
    """

    def __init__(self):
        self._runs: Dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        self._simulator = get_simulator()
        self._generator = ScenarioGenerator(base_dir=str(SCENARIOS_DIR))
        self._ensure_scenarios_generated()

    def _ensure_scenarios_generated(self):
        """Generate scenario files if they don't exist yet."""
        for scenario in ["four_way", "one_way", "two_way", "t_junction"]:
            paths = get_scenario_path(scenario, SCENARIOS_DIR)
            if not Path(paths["cfg"]).exists():
                logger.info("Generating scenario files for: %s", scenario)
                try:
                    self._generator.generate(scenario)
                except Exception as e:
                    logger.error("Failed to generate scenario %s: %s", scenario, e)

    @property
    def sumo_available(self) -> bool:
        return isinstance(self._simulator, SUMOSimulator) and self._simulator.is_available

    def submit_run(self,
                   scenario_type: str = "four_way",
                   demand: str = "normal",
                   disruption: str = "none",
                   intervention: Optional[dict] = None,
                   demand_scale: Optional[float] = None) -> str:
        """Submit a simulation run. Returns run_id immediately."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        record = RunRecord(
            run_id=run_id,
            scenario_type=scenario_type,
            demand=demand,
            disruption=disruption,
            intervention=intervention,
            status="QUEUED",
            created_at=time.time(),
        )
        with self._lock:
            self._runs[run_id] = record

        # Launch in background thread
        t = threading.Thread(
            target=self._execute_run,
            args=(run_id, scenario_type, demand, disruption, intervention, demand_scale),
            daemon=True
        )
        t.start()
        return run_id

    def _execute_run(self, run_id, scenario_type, demand, disruption, intervention, demand_scale):
        """Synchronously execute the simulation in a thread."""
        with self._lock:
            self._runs[run_id].status = "RUNNING"

        try:
            paths = get_scenario_path(scenario_type, SCENARIOS_DIR)
            profile = DEMAND_PROFILES.get(demand, DEMAND_PROFILES["normal"])
            capacity_factor = DISRUPTION_CAPACITY_FACTORS.get(disruption, 1.0)

            if demand_scale is None:
                demand_scale = profile["flow"] / 600.0  # normalize to base 600 vph

            scenario = SimulationScenario(
                scenario_id=f"{scenario_type}_{demand}_{disruption}",  # encodes type for zoom logic
                network_file=paths["net"],
                route_file=paths["rou"],
                demand_scale=demand_scale * capacity_factor,
                intervention=intervention,
                duration_steps=300,   # 300 steps at 1s = 5 minutes visual
                step_length_s=1,
            )

            raw = self._simulator.run_scenario(scenario)

            # Augment with scenario metadata for richer metrics
            metrics = self._build_metrics(raw, scenario_type, demand, disruption, capacity_factor)

            with self._lock:
                self._runs[run_id].status = "COMPLETED"
                self._runs[run_id].completed_at = time.time()
                self._runs[run_id].metrics = metrics

            logger.info("Run %s completed. Source: %s", run_id, raw.source)

        except Exception as e:
            logger.error("Run %s failed: %s", run_id, e, exc_info=True)
            with self._lock:
                self._runs[run_id].status = "FAILED"
                self._runs[run_id].error = str(e)
                self._runs[run_id].completed_at = time.time()

    def _build_metrics(self, raw: SimulationMetrics, scenario_type, demand, disruption, capacity_factor) -> dict:
        """Enrich raw simulation metrics with scenario context."""
        profile = DEMAND_PROFILES.get(demand, DEMAND_PROFILES["normal"])
        base_capacity_map = {
            "four_way": 3200,    # total vph through intersection
            "one_way": 5400,     # 3 lanes × 1800
            "two_way": 7200,     # 2 dirs × 2 lanes × 1800
            "t_junction": 5400,
        }
        capacity = base_capacity_map.get(scenario_type, 3600) * capacity_factor
        flow = profile["flow"]
        utilization = min(1.0, flow / max(capacity / 4, 1))

        return {
            "run_id": raw.scenario_id,
            "scenario_id": f"{scenario_type}_{demand}_{disruption}",
            "source": raw.source,
            "scenario_type": scenario_type,
            "demand_profile": demand,
            "disruption": disruption,
            "capacity_factor": capacity_factor,
            "capacity_utilization": round(utilization, 3),
            "mean_travel_time_s": round(raw.mean_travel_time_s, 2),
            "mean_speed_kmh": round(raw.mean_speed_kmh, 2),
            "mean_throughput_vph": round(raw.mean_throughput_vph, 2),
            "mean_queue_length_veh": round(raw.mean_queue_length_veh, 2),
            "total_delay_veh_h": round(raw.total_delay_veh_h, 2),
            "congested_segments": raw.congested_segments,
            "congestion_level": self._classify_util(utilization),
            "disclaimer": (
                f"Source: {raw.source}. "
                + ("These are real SUMO simulation results." if raw.source == "sumo_simulation"
                   else "SUMO not available — mock estimates shown. Install SUMO for real simulation.")
            ),
        }

    @staticmethod
    def _classify_util(util: float) -> str:
        if util >= 0.85: return "severe"
        if util >= 0.65: return "heavy"
        if util >= 0.40: return "moderate"
        return "free"

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            return self._runs.get(run_id)

    def get_run_status(self, run_id: str) -> dict:
        record = self.get_run(run_id)
        if record is None:
            return {"error": f"Run {run_id} not found"}
        return {
            "run_id": record.run_id,
            "status": record.status,
            "scenario_type": record.scenario_type,
            "demand": record.demand,
            "disruption": record.disruption,
            "created_at": record.created_at,
            "completed_at": record.completed_at,
            "elapsed_s": round((record.completed_at or time.time()) - record.created_at, 2),
        }

    def get_run_results(self, run_id: str) -> dict:
        record = self.get_run(run_id)
        if record is None:
            return {"error": f"Run {run_id} not found"}
        if record.status != "COMPLETED":
            return {"run_id": run_id, "status": record.status, "metrics": None}
        return {"run_id": run_id, "status": record.status, "metrics": record.metrics}

    def list_scenarios(self) -> list:
        return [
            {"id": "four_way",   "name": "4-Way Intersection", "description": "Signalised 4-arm junction"},
            {"id": "one_way",    "name": "1-Way Corridor",     "description": "Unidirectional 3-lane arterial"},
            {"id": "two_way",    "name": "2-Way Arterial",     "description": "Bidirectional 2-lane road"},
            {"id": "t_junction", "name": "T-Junction",         "description": "Signalised T-junction with minor approach"},
        ]


# Singleton
_manager_instance: Optional[ScenarioManager] = None


def get_scenario_manager() -> ScenarioManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ScenarioManager()
    return _manager_instance
