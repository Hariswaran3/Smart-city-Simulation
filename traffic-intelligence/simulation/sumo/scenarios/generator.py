"""
SUMO Scenario Generator
========================
Generates SUMO network + route + config files for all four scenario types.
Uses netconvert for valid net.xml. Routes are defined with proper <route>
tags (not same-edge from/to) so SUMO runs without route errors.
"""

import os
import logging
from pathlib import Path
from subprocess import run as sp_run, DEVNULL

logger = logging.getLogger(__name__)

DEMAND_PROFILES = {
    "normal":           {"vph": 600,  "flow": 600},
    "peak":             {"vph": 1400, "flow": 1400},
    "directional_peak": {"vph": 1600, "flow": 1600},
    "surge":            {"vph": 1800, "flow": 1800},
}

DISRUPTION_CAPACITY_FACTORS = {
    "none":       1.0,
    "accident":   0.4,
    "roadwork":   0.6,
    "lane_block": 0.5,
}

# Legacy alias
DISRUPTION_CAPACITY = DISRUPTION_CAPACITY_FACTORS


def get_scenario_path(scenario_type: str, base_dir: Path) -> dict:
    """Return paths dict for a scenario type."""
    d = Path(base_dir) / scenario_type
    name_map = {
        "four_way":   "four_way",
        "one_way":    "one_way",
        "two_way":    "two_way",
        "t_junction": "t_junction",
    }
    name = name_map.get(scenario_type, scenario_type)
    return {
        "net": str(d / f"{name}.net.xml"),
        "rou": str(d / f"{name}.rou.xml"),
        "cfg": str(d / f"{name}.sumocfg"),
    }



def _netconvert(nod: Path, edg: Path, out: Path) -> bool:
    """Call netconvert and return True on success."""
    result = sp_run(
        ["netconvert", "--node-files", str(nod), "--edge-files", str(edg), "-o", str(out)],
        stdout=DEVNULL, stderr=DEVNULL
    )
    return result.returncode == 0


def _sumocfg(d: Path, net: str, rou: str, name: str):
    """Write a .sumocfg file."""
    (d / f"{name}.sumocfg").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <input>
    <net-file value="{net}"/>
    <route-files value="{rou}"/>
  </input>
  <time>
    <begin value="0"/>
    <end value="3600"/>
    <step-length value="1"/>
  </time>
</configuration>
""", encoding="utf-8")


class ScenarioGenerator:
    """Generates SUMO scenario files for all four network types."""

    def __init__(self, base_dir: str = "simulation/sumo/scenarios"):
        self.base_dir = Path(base_dir)

    def generate_all(self):
        for s in ["four_way", "one_way", "two_way", "t_junction"]:
            self.generate(s)
        logger.info("All scenarios generated.")
        print("All scenarios generated.")

    def generate(self, scenario_type: str):
        d = self.base_dir / scenario_type
        d.mkdir(parents=True, exist_ok=True)
        generators = {
            "four_way":   self._gen_four_way,
            "one_way":    self._gen_one_way,
            "two_way":    self._gen_two_way,
            "t_junction": self._gen_t_junction,
        }
        fn = generators.get(scenario_type)
        if fn:
            fn(d)
            logger.info("Generated '%s' → %s", scenario_type, d)
            print(f"Generated '{scenario_type}'")
        else:
            raise ValueError(f"Unknown scenario: {scenario_type}")

    # ───────────────────────────── 4-WAY ────────────────────────────────────
    def _gen_four_way(self, d: Path):
        nod = d / "nodes.nod.xml"
        edg = d / "edges.edg.xml"
        nod.write_text("""<nodes>
  <node id="C" x="0"    y="0"    type="traffic_light"/>
  <node id="N" x="0"    y="300"  type="dead_end"/>
  <node id="S" x="0"    y="-300" type="dead_end"/>
  <node id="E" x="300"  y="0"    type="dead_end"/>
  <node id="W" x="-300" y="0"    type="dead_end"/>
</nodes>""", encoding="utf-8")
        edg.write_text("""<edges>
  <edge id="N2C" from="N" to="C" numLanes="2" speed="13.89"/>
  <edge id="C2N" from="C" to="N" numLanes="2" speed="13.89"/>
  <edge id="S2C" from="S" to="C" numLanes="2" speed="13.89"/>
  <edge id="C2S" from="C" to="S" numLanes="2" speed="13.89"/>
  <edge id="E2C" from="E" to="C" numLanes="2" speed="13.89"/>
  <edge id="C2E" from="C" to="E" numLanes="2" speed="13.89"/>
  <edge id="W2C" from="W" to="C" numLanes="2" speed="13.89"/>
  <edge id="C2W" from="C" to="W" numLanes="2" speed="13.89"/>
</edges>""", encoding="utf-8")
        net = d / "four_way.net.xml"
        if not _netconvert(nod, edg, net):
            logger.error("netconvert failed for four_way")

        rou = d / "four_way.rou.xml"
        rou.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<routes>
  <vType id="car"   accel="2.6" decel="4.5" sigma="0.5" length="4.5"  maxSpeed="13.89" color="yellow"/>
  <vType id="truck" accel="1.3" decel="3.5" sigma="0.5" length="12.0" maxSpeed="11.11" color="1,0.5,0"/>
  <vType id="bus"   accel="1.5" decel="3.8" sigma="0.5" length="12.0" maxSpeed="11.11" color="0,0.8,0"/>

  <!-- Through routes -->
  <route id="NS" edges="N2C C2S"/>
  <route id="SN" edges="S2C C2N"/>
  <route id="EW" edges="E2C C2W"/>
  <route id="WE" edges="W2C C2E"/>
  <!-- Turn routes -->
  <route id="NE" edges="N2C C2E"/>
  <route id="NW" edges="N2C C2W"/>
  <route id="SE" edges="S2C C2E"/>
  <route id="SW" edges="S2C C2W"/>
  <route id="EN" edges="E2C C2N"/>
  <route id="ES" edges="E2C C2S"/>
  <route id="WN" edges="W2C C2N"/>
  <route id="WS" edges="W2C C2S"/>

  <flow id="f0"  type="car"   route="NS" begin="0" end="3600" vehsPerHour="500" departLane="best" departSpeed="max"/>
  <flow id="f1"  type="car"   route="SN" begin="0" end="3600" vehsPerHour="480" departLane="best" departSpeed="max"/>
  <flow id="f2"  type="car"   route="EW" begin="0" end="3600" vehsPerHour="450" departLane="best" departSpeed="max"/>
  <flow id="f3"  type="car"   route="WE" begin="0" end="3600" vehsPerHour="470" departLane="best" departSpeed="max"/>
  <flow id="f4"  type="car"   route="NE" begin="0" end="3600" vehsPerHour="120" departLane="best" departSpeed="max"/>
  <flow id="f5"  type="car"   route="NW" begin="0" end="3600" vehsPerHour="100" departLane="best" departSpeed="max"/>
  <flow id="f6"  type="car"   route="SE" begin="0" end="3600" vehsPerHour="110" departLane="best" departSpeed="max"/>
  <flow id="f7"  type="car"   route="SW" begin="0" end="3600" vehsPerHour="90"  departLane="best" departSpeed="max"/>
  <flow id="f8"  type="truck" route="NS" begin="0" end="3600" vehsPerHour="60"  departLane="best" departSpeed="max"/>
  <flow id="f9"  type="truck" route="EW" begin="0" end="3600" vehsPerHour="55"  departLane="best" departSpeed="max"/>
  <flow id="f10" type="bus"   route="WE" begin="0" end="3600" vehsPerHour="30"  departLane="best" departSpeed="max"/>
</routes>
""", encoding="utf-8")
        _sumocfg(d, "four_way.net.xml", "four_way.rou.xml", "four_way")

    # ───────────────────────────── 1-WAY ────────────────────────────────────
    def _gen_one_way(self, d: Path):
        nod = d / "nodes.nod.xml"
        edg = d / "edges.edg.xml"
        nod.write_text("""<nodes>
  <node id="A" x="0"    y="0"/>
  <node id="B" x="500"  y="0"/>
  <node id="C" x="1000" y="0"/>
  <node id="D" x="1500" y="0"/>
</nodes>""", encoding="utf-8")
        edg.write_text("""<edges>
  <edge id="AB" from="A" to="B" numLanes="3" speed="16.67"/>
  <edge id="BC" from="B" to="C" numLanes="3" speed="16.67"/>
  <edge id="CD" from="C" to="D" numLanes="3" speed="16.67"/>
</edges>""", encoding="utf-8")
        net = d / "one_way.net.xml"
        if not _netconvert(nod, edg, net):
            logger.error("netconvert failed for one_way")

        rou = d / "one_way.rou.xml"
        rou.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<routes>
  <vType id="car"   accel="2.6" decel="4.5" sigma="0.5" length="4.5"  maxSpeed="16.67" color="yellow"/>
  <vType id="truck" accel="1.3" decel="3.5" sigma="0.5" length="12.0" maxSpeed="11.11" color="1,0.5,0"/>

  <route id="thru" edges="AB BC CD"/>
  <route id="half" edges="AB BC"/>

  <flow id="main"  type="car"   route="thru" begin="0" end="3600" vehsPerHour="1200" departLane="best" departSpeed="max"/>
  <flow id="short" type="car"   route="half" begin="0" end="3600" vehsPerHour="200"  departLane="best" departSpeed="max"/>
  <flow id="trucks" type="truck" route="thru" begin="0" end="3600" vehsPerHour="120" departLane="best" departSpeed="max"/>
</routes>
""", encoding="utf-8")
        _sumocfg(d, "one_way.net.xml", "one_way.rou.xml", "one_way")

    # ───────────────────────────── 2-WAY ────────────────────────────────────
    def _gen_two_way(self, d: Path):
        nod = d / "nodes.nod.xml"
        edg = d / "edges.edg.xml"
        nod.write_text("""<nodes>
  <node id="W"   x="0"    y="0"/>
  <node id="MID" x="500"  y="0"/>
  <node id="E"   x="1000" y="0"/>
</nodes>""", encoding="utf-8")
        edg.write_text("""<edges>
  <edge id="W_MID"  from="W"   to="MID" numLanes="2" speed="13.89"/>
  <edge id="MID_E"  from="MID" to="E"   numLanes="2" speed="13.89"/>
  <edge id="E_MID"  from="E"   to="MID" numLanes="2" speed="13.89"/>
  <edge id="MID_W"  from="MID" to="W"   numLanes="2" speed="13.89"/>
</edges>""", encoding="utf-8")
        net = d / "two_way.net.xml"
        if not _netconvert(nod, edg, net):
            logger.error("netconvert failed for two_way")

        rou = d / "two_way.rou.xml"
        rou.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<routes>
  <vType id="car"   accel="2.6" decel="4.5" sigma="0.5" length="4.5"  maxSpeed="13.89" color="yellow"/>
  <vType id="truck" accel="1.3" decel="3.5" sigma="0.5" length="12.0" maxSpeed="11.11" color="1,0.5,0"/>

  <route id="EB" edges="W_MID MID_E"/>
  <route id="WB" edges="E_MID MID_W"/>

  <flow id="eb_car"   type="car"   route="EB" begin="0" end="3600" vehsPerHour="900" departLane="best" departSpeed="max"/>
  <flow id="eb_truck" type="truck" route="EB" begin="0" end="3600" vehsPerHour="100" departLane="best" departSpeed="max"/>
  <flow id="wb_car"   type="car"   route="WB" begin="0" end="3600" vehsPerHour="500" departLane="best" departSpeed="max"/>
  <flow id="wb_truck" type="truck" route="WB" begin="0" end="3600" vehsPerHour="60"  departLane="best" departSpeed="max"/>
</routes>
""", encoding="utf-8")
        _sumocfg(d, "two_way.net.xml", "two_way.rou.xml", "two_way")

    # ───────────────────────────── T-JUNCTION ───────────────────────────────
    def _gen_t_junction(self, d: Path):
        nod = d / "nodes.nod.xml"
        edg = d / "edges.edg.xml"
        nod.write_text("""<nodes>
  <node id="W"  x="-500" y="0"    type="dead_end"/>
  <node id="J"  x="0"    y="0"    type="traffic_light"/>
  <node id="E"  x="500"  y="0"    type="dead_end"/>
  <node id="N"  x="0"    y="300"  type="dead_end"/>
</nodes>""", encoding="utf-8")
        edg.write_text("""<edges>
  <edge id="W2J" from="W" to="J" numLanes="2" speed="13.89"/>
  <edge id="J2W" from="J" to="W" numLanes="2" speed="13.89"/>
  <edge id="E2J" from="E" to="J" numLanes="2" speed="13.89"/>
  <edge id="J2E" from="J" to="E" numLanes="2" speed="13.89"/>
  <edge id="N2J" from="N" to="J" numLanes="1" speed="11.11"/>
  <edge id="J2N" from="J" to="N" numLanes="1" speed="11.11"/>
</edges>""", encoding="utf-8")
        net = d / "t_junction.net.xml"
        if not _netconvert(nod, edg, net):
            logger.error("netconvert failed for t_junction")

        rou = d / "t_junction.rou.xml"
        rou.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<routes>
  <vType id="car"   accel="2.6" decel="4.5" sigma="0.5" length="4.5"  maxSpeed="13.89" color="yellow"/>
  <vType id="truck" accel="1.3" decel="3.5" sigma="0.5" length="12.0" maxSpeed="11.11" color="1,0.5,0"/>

  <route id="WE"  edges="W2J J2E"/>
  <route id="EW"  edges="E2J J2W"/>
  <route id="NE"  edges="N2J J2E"/>
  <route id="NW"  edges="N2J J2W"/>

  <flow id="f_we"    type="car"   route="WE"  begin="0" end="3600" vehsPerHour="900" departLane="best" departSpeed="max"/>
  <flow id="f_ew"    type="car"   route="EW"  begin="0" end="3600" vehsPerHour="700" departLane="best" departSpeed="max"/>
  <flow id="f_ne"    type="car"   route="NE"  begin="0" end="3600" vehsPerHour="300" departLane="best" departSpeed="max"/>
  <flow id="f_nw"    type="car"   route="NW"  begin="0" end="3600" vehsPerHour="150" departLane="best" departSpeed="max"/>
  <flow id="f_truck" type="truck" route="WE"  begin="0" end="3600" vehsPerHour="80"  departLane="best" departSpeed="max"/>
</routes>
""", encoding="utf-8")
        _sumocfg(d, "t_junction.net.xml", "t_junction.rou.xml", "t_junction")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gen = ScenarioGenerator()
    gen.generate_all()
