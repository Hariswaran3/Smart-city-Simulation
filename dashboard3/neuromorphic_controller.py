#!/usr/bin/env python3
"""
neuromorphic_controller.py
Simple event-driven LIF-style controller for a 4-way SUMO intersection.

Usage:
  1) Ensure SUMO_HOME is set.
  2) Put this script in the folder with simulation.sumocfg and network.net.xml
  3) python neuromorphic_controller.py
"""

import os, sys, math, time
import numpy as np
from collections import OrderedDict

# --- Ensure SUMO tools on PYTHONPATH ---
if "SUMO_HOME" not in os.environ:
    raise SystemExit("Set SUMO_HOME environment variable to your SUMO installation path.")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci
import sumolib

# -------- CONFIG --------
SUMO_BINARY = "sumo-gui"     # GUI enabled for visual monitoring
SUMO_CFG = "simulation.sumocfg"
SUMO_STEP = 0.1              # Faster response time
SIM_DURATION = 300           # seconds
THRESHOLD_QUEUE = 4          # queue length threshold to emit a spike
INPUT_WEIGHT = 1.0
# weight matrix: shape (2 outputs x N_inputs). Will be resized later if needed.
# Note: values are tunable.
DEFAULT_W = np.array([[1.0, 1.0, 0.3, 0.3],
                      [0.3, 0.3, 1.0, 1.0]])
v_rest = 0.0
v_reset = 0.0
v_thresh = 1.0
tau = 0.6                    # membrane time constant (s)
min_green = 5.0              # minimum green time (s)
# ------------------------

def start_sumo():
    cmd = [SUMO_BINARY, "-c", SUMO_CFG, "--step-length", str(SUMO_STEP)]
    print("Starting SUMO:", " ".join(cmd))
    traci.start(cmd)

def detect_tl_and_select_lanes():
    tls = traci.trafficlight.getIDList()
    if not tls:
        raise SystemExit("No traffic lights found in the network.")
    tl_id = tls[0]
    print("Using traffic light:", tl_id)

    # controlled links (each link is a triple (fromLane, toLane, via))
    controlled_links = traci.trafficlight.getControlledLinks(tl_id)
    from_lanes = []
    for group in controlled_links:
        for link in group:
            from_lanes.append(link[0])
    # group lanes by edge (incoming road)
    edge_to_lanes = OrderedDict()
    for lane in from_lanes:
        edge = traci.lane.getEdgeID(lane)
        if edge not in edge_to_lanes:
            edge_to_lanes[edge] = []
        edge_to_lanes[edge].append(lane)
    # select up to 4 unique incoming edges (keeps order)
    selected_edges = list(edge_to_lanes.keys())[:4]
    selected_lanes = [edge_to_lanes[e][0] for e in selected_edges]
    print("Selected edges:", selected_edges)
    print("Selected lanes (one per incoming edge):", selected_lanes)
    return tl_id, selected_lanes, selected_edges, from_lanes

def classify_edges_direction(net, edges):
    # compute approximate direction (N,S,E,W) per edge using node coords
    directions = {}
    for e in edges:
        edge = net.getEdge(e)
        x0, y0 = edge.getFromNode().getCoord()
        x1, y1 = edge.getToNode().getCoord()
        dx = x1 - x0; dy = y1 - y0
        ang = math.degrees(math.atan2(dy, dx))
        if -45 <= ang <= 45:
            d = 'E'
        elif 45 < ang <= 135:
            d = 'N'
        elif ang > 135 or ang <= -135:
            d = 'W'
        else:
            d = 'S'
        directions[e] = d
    return directions

def auto_map_phases(tl_id, directions, from_lanes):
    # from_lanes: flattened order matching phase state chars
    # map each from_lane to 'NS' or 'EW' by its edge's direction
    lane_groups = []
    for lane in from_lanes:
        e = traci.lane.getEdgeID(lane)
        d = directions.get(e, None)
        grp = 'NS' if d in ('N','S') else 'EW'
        lane_groups.append(grp)

    # read phase strings
    defs = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl_id)
    # defs is a list; use first program
    program = defs[0]
    # get phase strings robustly:
    try:
        phase_states = [p.state for p in program.phases]
    except Exception:
        phase_states = [p.get('state') for p in program.getPhases()]

    ns_counts = []
    ew_counts = []
    for state in phase_states:
        ns = 0; ew = 0
        for i, ch in enumerate(state):
            if ch.upper() == 'G':
                if lane_groups[i] == 'NS':
                    ns += 1
                else:
                    ew += 1
        ns_counts.append(ns); ew_counts.append(ew)
    ns_phase = int(np.argmax(ns_counts))
    ew_phase = int(np.argmax(ew_counts))
    print("Detected phase mapping: NS phase index =", ns_phase, ", EW phase index =", ew_phase)
    return ns_phase, ew_phase

def run_controller():
    start_sumo()
    tl_id, lanes, edges, from_lanes = detect_tl_and_select_lanes()
    net = sumolib.net.readNet("network.net.xml")   # make sure file in same folder
    directions = classify_edges_direction(net, edges)
    ns_phase, ew_phase = auto_map_phases(tl_id, directions, from_lanes)

    N_in = len(lanes)
    W = DEFAULT_W.copy()
    if W.shape[1] != N_in:
        # reshape default weights if lane count differs
        W = np.ones((2, N_in)) * 0.5
        # bias: first two -> NS, last two -> EW if possible
        for i in range(N_in):
            if i < N_in/2:
                W[0, i] = 1.0
            else:
                W[1, i] = 1.0

    v_out = np.zeros(2)
    last_phase = traci.trafficlight.getPhase(tl_id)
    last_change = traci.simulation.getTime()
    sim_end = SIM_DURATION

    print("Controller running for", sim_end, "s. Initial phase:", last_phase)
    while traci.simulation.getTime() < sim_end:
        traci.simulationStep()
        t = traci.simulation.getTime()
        # read queue lengths for selected lanes
        qs = [traci.lane.getLastStepVehicleNumber(l) for l in lanes]
        # encode spikes: simple pulse = max(queue - threshold, 0)
        inp = np.maximum(np.array(qs) - THRESHOLD_QUEUE, 0) * INPUT_WEIGHT
        # simple LIF Euler update (one step = SUMO_STEP)
        dv = (-v_out + (W @ inp)) * (SUMO_STEP / tau)
        v_out += dv
        # detect firing
        fired = np.where(v_out >= v_thresh)[0]
        if fired.size > 0:
            # choose the neuron with largest voltage (tie-break)
            chosen = int(fired[np.argmax(v_out[fired])])
            chosen_phase = ns_phase if chosen == 0 else ew_phase
            # only change if min_green passed OR same phase (extend)
            if (t - last_change >= min_green) or (chosen_phase == last_phase):
                if chosen_phase != last_phase:
                    traci.trafficlight.setPhase(tl_id, chosen_phase)
                    print(f"[{t:.1f}s] switching to phase {chosen_phase} (output {chosen}), queues={qs}")
                    last_phase = chosen_phase
                    last_change = t
                else:
                    # same phase: keep it (acts as small extension)
                    print(f"[{t:.1f}s] output {chosen} fired — keeping phase {chosen_phase}, queues={qs}")
            v_out[chosen] = v_reset
        # small passive decay
        v_out *= 0.995

    traci.close()
    print("Simulation finished.")

if __name__ == "__main__":
    run_controller()