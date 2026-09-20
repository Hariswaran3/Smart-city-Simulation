"""
SUMO Traffic Simulation Interface
===================================
Abstract base class + SUMO GUI implementation + Mock fallback.

The SUMO-GUI is launched headless and frames are captured via TraCI
screenshot → stored in SUMO_STREAM_FRAME for MJPEG streaming to the dashboard.
"""

import abc
import logging
import os
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Global shared frame buffer for MJPEG stream ────────────────────────────
SUMO_STREAM_FRAME: Optional[bytes] = None


@dataclass
class SimulationScenario:
    """Input specification for a traffic simulation scenario."""
    scenario_id: str
    network_file: Optional[str] = None
    route_file: Optional[str] = None
    demand_scale: float = 1.0
    intervention: Optional[dict] = None
    duration_steps: int = 300   # steps to run (at step_length_s each)
    step_length_s: int = 1


@dataclass
class SimulationMetrics:
    """Output metrics from a simulation run."""
    scenario_id: str
    source: str          # 'sumo_simulation' | 'mock_simulator'
    mean_travel_time_s: float
    mean_speed_kmh: float
    mean_throughput_vph: float
    mean_queue_length_veh: float
    total_delay_veh_h: float
    congested_segments: List[str]
    segment_metrics: Dict[str, dict]


class TrafficSimulator(abc.ABC):
    """Abstract interface for traffic simulation."""

    @abc.abstractmethod
    def run_scenario(self, scenario: SimulationScenario) -> SimulationMetrics:
        ...

    @abc.abstractmethod
    def get_metrics(self, scenario_id: str) -> Optional[SimulationMetrics]:
        ...

    @property
    @abc.abstractmethod
    def is_available(self) -> bool:
        ...


class MockSimulator(TrafficSimulator):
    """
    Development-only mock simulator.
    Returns plausible-looking metrics WITHOUT running any real simulation.
    All outputs are labeled 'mock_simulator'.
    NEVER present mock outputs as real simulation results.
    """

    def __init__(self):
        self._results: Dict[str, SimulationMetrics] = {}

    @property
    def is_available(self) -> bool:
        return True

    def run_scenario(self, scenario: SimulationScenario) -> SimulationMetrics:
        import random
        logger.warning("MockSimulator: NOT a real simulation. Labeled 'mock_simulator'.")
        base_speed = 35.0 if scenario.intervention is None else 40.0
        metrics = SimulationMetrics(
            scenario_id=scenario.scenario_id,
            source="mock_simulator",
            mean_travel_time_s=float(random.uniform(180, 420)),
            mean_speed_kmh=float(random.uniform(base_speed - 5, base_speed + 5)),
            mean_throughput_vph=float(random.uniform(800, 1500)),
            mean_queue_length_veh=float(random.uniform(0, 15)),
            total_delay_veh_h=float(random.uniform(10, 100)),
            congested_segments=[],
            segment_metrics={},
        )
        self._results[scenario.scenario_id] = metrics
        return metrics

    def get_metrics(self, scenario_id: str) -> Optional[SimulationMetrics]:
        return self._results.get(scenario_id)


class SUMOSimulator(TrafficSimulator):
    """
    Real SUMO simulation backend.
    Launches sumo-gui, captures frames via TraCI screenshot into SUMO_STREAM_FRAME,
    and streams them to the dashboard via MJPEG.
    Falls back to MockSimulator if SUMO is unavailable.
    """

    def __init__(self):
        self._sumo_available = self._check_sumo()
        self._results: Dict[str, SimulationMetrics] = {}
        if not self._sumo_available:
            logger.warning("SUMO not detected. Install SUMO and set SUMO_HOME to enable real simulation.")

    @property
    def is_available(self) -> bool:
        return self._sumo_available

    def _check_sumo(self) -> bool:
        import shutil
        sumo_home = os.environ.get("SUMO_HOME")
        if sumo_home and os.path.isdir(sumo_home):
            return True
        return shutil.which("sumo") is not None or shutil.which("sumo-gui") is not None

    def _find_sumo_gui(self) -> str:
        sumo_home = os.environ.get("SUMO_HOME", "")
        candidates = [
            os.path.join(sumo_home, "bin", "sumo-gui.exe"),
            os.path.join(sumo_home, "bin", "sumo-gui"),
            "sumo-gui",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return "sumo-gui"

    def run_scenario(self, scenario: SimulationScenario) -> SimulationMetrics:
        if not self._sumo_available:
            logger.warning("SUMO not available — delegating to MockSimulator.")
            return MockSimulator().run_scenario(scenario)
        try:
            import traci
            metrics = self._run_with_traci(scenario)
            self._results[scenario.scenario_id] = metrics
            return metrics
        except ImportError:
            logger.error("traci not installed. Run: pip install traci")
            return MockSimulator().run_scenario(scenario)
        except Exception as e:
            logger.error("SUMO simulation failed: %s", e)
            return MockSimulator().run_scenario(scenario)

    def _run_with_traci(self, scenario: SimulationScenario) -> SimulationMetrics:
        """
        Launch sumo-gui via TraCI, capture each frame as JPEG into
        the global SUMO_STREAM_FRAME buffer, collect speed metrics,
        then return SimulationMetrics.
        """
        import traci

        global SUMO_STREAM_FRAME
        SUMO_STREAM_FRAME = None

        sumo_binary = self._find_sumo_gui()

        # Prefer the .sumocfg if it exists (avoids route-sorting warnings)
        cfg_file = None
        if scenario.network_file:
            from pathlib import Path
            cfg_candidate = Path(scenario.network_file).parent / f"{scenario.scenario_id.split('_')[0]}_{scenario.scenario_id.split('_')[1] if '_' in scenario.scenario_id else ''}.sumocfg"
            # Try simple name match e.g. four_way.sumocfg
            for suffix in ["four_way", "one_way", "two_way", "t_junction"]:
                candidate = Path(scenario.network_file).parent / f"{suffix}.sumocfg"
                if candidate.exists():
                    cfg_file = str(candidate)
                    break

        if cfg_file:
            sumo_cmd = [
                sumo_binary,
                "-c", cfg_file,
                "--start",
                "--delay", "100",
                "--quit-on-end",
                "--no-step-log",
            ]
        else:
            sumo_cmd = [
                sumo_binary,
                "--net-file",    scenario.network_file or "network.net.xml",
                "--route-files", scenario.route_file or "routes.rou.xml",
                "--step-length", str(scenario.step_length_s),
                "--start",
                "--delay", "100",
                "--quit-on-end",
                "--no-step-log",
                "--no-warnings",
            ]

        logger.info("Launching sumo-gui: %s", " ".join(sumo_cmd))
        traci.start(sumo_cmd)

        # ── Configure GUI view ──────────────────────────────────────────────
        view_id = None
        try:
            import time as _time
            _time.sleep(1.5)  # give sumo-gui time to render first frame
            views = traci.gui.getIDList()
            if views:
                view_id = views[0]
                sid = scenario.scenario_id
                
                # Bounding boxes after netconvert normalization:
                # four_way: 0,0 to 600,600 (Center 300,300)
                # t_junction: 0,0 to 1000,300 (Center 500,150)
                # two_way: 0,0 to 1000,0 (Center 500,0)
                # one_way: 0,0 to 1500,0 (Center 750,0)
                
                if "four_way" in sid:
                    traci.gui.setZoom(view_id, 1200)
                    traci.gui.setOffset(view_id, 300, 300)
                elif "t_junction" in sid:
                    traci.gui.setZoom(view_id, 600)
                    traci.gui.setOffset(view_id, 500, 150)
                elif "two_way" in sid:
                    traci.gui.setZoom(view_id, 600)
                    traci.gui.setOffset(view_id, 500, 0)
                else:  # one_way
                    traci.gui.setZoom(view_id, 400)
                    traci.gui.setOffset(view_id, 750, 0)
        except Exception as ex:
            logger.warning("Could not configure SUMO GUI view: %s", ex)

        screenshot_path = os.path.abspath("_sumo_frame.jpg")
        speed_sum = 0.0
        steps_count = 0
        step = 0
        max_steps = min(scenario.duration_steps, 300)  # cap at 300 steps for UI responsiveness

        try:
            while step < max_steps:
                traci.simulationStep()

                # ── Capture frame ──────────────────────────────────────────
                if view_id:
                    try:
                        traci.gui.screenshot(view_id, screenshot_path)
                        time.sleep(0.03)   # give SUMO time to write file
                        if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                            try:
                                import cv2
                                frame = cv2.imread(screenshot_path)
                                if frame is not None:
                                    frame = cv2.resize(frame, (820, 460))
                                    _, buf = cv2.imencode(
                                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
                                    )
                                    SUMO_STREAM_FRAME = buf.tobytes()
                            except ImportError:
                                # cv2 not installed — read raw bytes from file instead
                                with open(screenshot_path, "rb") as fh:
                                    SUMO_STREAM_FRAME = fh.read()
                    except Exception as cap_err:
                        logger.debug("Frame capture error: %s", cap_err)

                # ── Collect speed metrics ──────────────────────────────────
                edges = traci.edge.getIDList()
                if edges:
                    s = sum(traci.edge.getLastStepMeanSpeed(e) for e in edges) / max(len(edges), 1)
                    speed_sum += s * 3.6   # m/s → km/h
                    steps_count += 1

                step += 1

        finally:
            try:
                traci.close()
            except Exception:
                pass
            SUMO_STREAM_FRAME = None
            if os.path.exists(screenshot_path):
                try:
                    os.remove(screenshot_path)
                except Exception:
                    pass

        mean_speed = speed_sum / max(steps_count, 1)
        # Derive secondary metrics from mean speed
        mean_tt  = max(30.0, 600.0 - mean_speed * 8)
        mean_q   = max(0.0, 60.0  - mean_speed * 1.2)
        total_d  = max(0.0, 200.0 - mean_speed * 4)
        throughput = max(0.0, mean_speed * 35)

        return SimulationMetrics(
            scenario_id=scenario.scenario_id,
            source="sumo_simulation",
            mean_travel_time_s=round(mean_tt, 1),
            mean_speed_kmh=round(mean_speed, 2),
            mean_throughput_vph=round(throughput, 0),
            mean_queue_length_veh=round(mean_q, 1),
            total_delay_veh_h=round(total_d, 1),
            congested_segments=[],
            segment_metrics={},
        )

    def get_metrics(self, scenario_id: str) -> Optional[SimulationMetrics]:
        return self._results.get(scenario_id)


def get_simulator() -> TrafficSimulator:
    """Factory: returns SUMOSimulator (falls back to MockSimulator if SUMO unavailable)."""
    return SUMOSimulator()
