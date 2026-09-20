#!/usr/bin/env python3
"""
neuromorphic_stdp_controller.py
Self-learning neuromorphic traffic controller with STDP (Spike-Timing Dependent Plasticity)
"""

import os, sys, math, time
import numpy as np
from collections import OrderedDict

if "SUMO_HOME" not in os.environ:
    raise SystemExit("Set SUMO_HOME environment variable to your SUMO installation path.")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci
import sumolib

# -------- CONFIG --------
SUMO_BINARY = "sumo-gui"
SUMO_CFG = "simulation.sumocfg"
SUMO_STEP = 0.1
SIM_DURATION = 300
THRESHOLD_QUEUE = 4
INPUT_WEIGHT = 1.0

# STDP Learning parameters
LEARNING_RATE = 0.01
REWARD_WINDOW = 10.0  # seconds to measure performance

DEFAULT_W = np.array([[1.0, 1.0, 0.3, 0.3],
                      [0.3, 0.3, 1.0, 1.0]])
v_rest = 0.0
v_reset = 0.0
v_thresh = 1.0
tau = 0.6
min_green = 5.0

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

    controlled_links = traci.trafficlight.getControlledLinks(tl_id)
    from_lanes = []
    for group in controlled_links:
        for link in group:
            from_lanes.append(link[0])
    
    edge_to_lanes = OrderedDict()
    for lane in from_lanes:
        edge = traci.lane.getEdgeID(lane)
        if edge not in edge_to_lanes:
            edge_to_lanes[edge] = []
        edge_to_lanes[edge].append(lane)
    
    selected_edges = list(edge_to_lanes.keys())[:4]
    selected_lanes = [edge_to_lanes[e][0] for e in selected_edges]
    print("Selected edges:", selected_edges)
    print("Selected lanes:", selected_lanes)
    return tl_id, selected_lanes, selected_edges, from_lanes

def classify_edges_direction(net, edges):
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
    lane_groups = []
    for lane in from_lanes:
        e = traci.lane.getEdgeID(lane)
        d = directions.get(e, None)
        grp = 'NS' if d in ('N','S') else 'EW'
        lane_groups.append(grp)

    defs = traci.trafficlight.getCompleteRedYellowGreenDefinition(tl_id)
    program = defs[0]
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
    print("Detected phase mapping: NS =", ns_phase, ", EW =", ew_phase)
    return ns_phase, ew_phase

def calculate_reward(lanes, prev_queues, current_queues):
    """Calculate reward based on queue reduction"""
    if prev_queues is None:
        return 0.0
    
    prev_total = sum(prev_queues)
    current_total = sum(current_queues)
    
    # Reward for reducing total queue length
    reward = (prev_total - current_total) / max(prev_total, 1)
    return reward

def stdp_update(W, inp, chosen, reward, learning_rate):
    """STDP learning rule: strengthen connections that led to good outcomes"""
    if reward > 0:  # Good outcome
        # Strengthen connections to winning neuron
        W[chosen] += learning_rate * reward * inp
        # Weaken connections to losing neuron
        other = 1 - chosen
        W[other] -= learning_rate * reward * inp * 0.5
    
    # Keep weights in reasonable bounds
    W = np.clip(W, 0.1, 2.0)
    return W

def run_controller():
    start_sumo()
    tl_id, lanes, edges, from_lanes = detect_tl_and_select_lanes()
    net = sumolib.net.readNet("network.net.xml")
    directions = classify_edges_direction(net, edges)
    ns_phase, ew_phase = auto_map_phases(tl_id, directions, from_lanes)

    N_in = len(lanes)
    W = DEFAULT_W.copy()
    if W.shape[1] != N_in:
        W = np.ones((2, N_in)) * 0.5
        for i in range(N_in):
            if i < N_in/2:
                W[0, i] = 1.0
            else:
                W[1, i] = 1.0

    v_out = np.zeros(2)
    last_phase = traci.trafficlight.getPhase(tl_id)
    last_change = traci.simulation.getTime()
    
    # STDP learning variables
    prev_queues = None
    reward_history = []
    learning_step = 0

    print("🧠 STDP Learning Controller running...")
    print("Initial weights:")
    print(f"NS neuron: {W[0]}")
    print(f"EW neuron: {W[1]}")
    
    while traci.simulation.getTime() < SIM_DURATION:
        traci.simulationStep()
        t = traci.simulation.getTime()
        
        qs = [traci.lane.getLastStepVehicleNumber(l) for l in lanes]
        inp = np.maximum(np.array(qs) - THRESHOLD_QUEUE, 0) * INPUT_WEIGHT
        
        # Calculate reward for learning
        reward = calculate_reward(lanes, prev_queues, qs)
        if reward != 0:
            reward_history.append(reward)
        
        # LIF neuron dynamics
        dv = (-v_out + (W @ inp)) * (SUMO_STEP / tau)
        v_out += dv
        
        fired = np.where(v_out >= v_thresh)[0]
        if fired.size > 0:
            chosen = int(fired[np.argmax(v_out[fired])])
            chosen_phase = ns_phase if chosen == 0 else ew_phase
            
            if (t - last_change >= min_green) or (chosen_phase == last_phase):
                if chosen_phase != last_phase:
                    traci.trafficlight.setPhase(tl_id, chosen_phase)
                    print(f"[{t:.1f}s] switching to phase {chosen_phase} (neuron {chosen}), queues={qs}")
                    last_phase = chosen_phase
                    last_change = t
                    
                    # STDP Learning: Update weights based on recent performance
                    if len(reward_history) > 0:
                        avg_reward = np.mean(reward_history[-5:])  # Recent performance
                        W = stdp_update(W, inp, chosen, avg_reward, LEARNING_RATE)
                        learning_step += 1
                        
                        if learning_step % 10 == 0:  # Print learning progress
                            print(f"🎓 Learning step {learning_step}: avg_reward={avg_reward:.3f}")
                            print(f"   Updated weights - NS: {W[0]}, EW: {W[1]}")
                
                else:
                    print(f"[{t:.1f}s] neuron {chosen} fired — keeping phase {chosen_phase}, queues={qs}")
            
            v_out[chosen] = v_reset
        
        v_out *= 0.995
        prev_queues = qs.copy()

    traci.close()
    
    print("\n🎯 FINAL LEARNING RESULTS:")
    print(f"Total learning steps: {learning_step}")
    print(f"Final weights:")
    print(f"NS neuron: {W[0]}")
    print(f"EW neuron: {W[1]}")
    if reward_history:
        print(f"Average reward: {np.mean(reward_history):.3f}")
    print("Simulation finished with STDP learning!")

if __name__ == "__main__":
    run_controller()