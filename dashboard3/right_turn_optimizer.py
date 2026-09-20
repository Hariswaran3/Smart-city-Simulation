#!/usr/bin/env python3
"""
Right-turn traffic optimizer
Adds intelligent right-turn management to reduce congestion
"""

import os, sys
import numpy as np

if "SUMO_HOME" not in os.environ:
    raise SystemExit("Set SUMO_HOME environment variable")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci

class RightTurnOptimizer:
    def __init__(self, tl_id, lanes):
        self.tl_id = tl_id
        self.lanes = lanes
        self.right_turn_threshold = 3  # Minimum right-turn vehicles to trigger optimization
        self.right_turn_green_time = 8  # Seconds of dedicated right-turn green
        
    def analyze_right_turns(self):
        """Analyze right-turn demand at intersection"""
        right_turn_data = {}
        
        for lane in self.lanes:
            right_turn_vehicles = []
            total_vehicles = traci.lane.getLastStepVehicleIDs(lane)
            
            for veh_id in total_vehicles:
                try:
                    route = traci.vehicle.getRoute(veh_id)
                    current_edge = traci.vehicle.getRoadID(veh_id)
                    
                    if len(route) > 1 and current_edge in route:
                        current_idx = route.index(current_edge)
                        if current_idx < len(route) - 1:
                            next_edge = route[current_idx + 1]
                            
                            # Check if it's a right turn
                            if self._is_right_turn(current_edge, next_edge):
                                wait_time = traci.vehicle.getWaitingTime(veh_id)
                                position = traci.vehicle.getLanePosition(veh_id)
                                right_turn_vehicles.append({
                                    'id': veh_id,
                                    'wait_time': wait_time,
                                    'position': position
                                })
                except:
                    continue
            
            right_turn_data[lane] = right_turn_vehicles
        
        return right_turn_data
    
    def _is_right_turn(self, from_edge, to_edge):
        """Check if movement is a right turn"""
        right_turns = {
            'N2C': 'C2E',  # North to East
            'E2C': 'C2S',  # East to South  
            'S2C': 'C2W',  # South to West
            'W2C': 'C2N'   # West to North
        }
        return right_turns.get(from_edge) == to_edge
    
    def should_optimize_right_turns(self):
        """Determine if right-turn optimization is needed"""
        right_turn_data = self.analyze_right_turns()
        
        total_right_turn_vehicles = 0
        max_wait_time = 0
        
        for lane, vehicles in right_turn_data.items():
            total_right_turn_vehicles += len(vehicles)
            if vehicles:
                max_wait_time = max(max_wait_time, max(v['wait_time'] for v in vehicles))
        
        # Optimize if many right-turn vehicles or long wait times
        return (total_right_turn_vehicles >= self.right_turn_threshold or 
                max_wait_time > 15)  # 15 seconds wait threshold
    
    def get_optimization_recommendation(self):
        """Get recommendation for right-turn optimization"""
        right_turn_data = self.analyze_right_turns()
        
        # Find direction with most right-turn demand
        direction_demand = {'NS': 0, 'EW': 0}
        
        for lane, vehicles in right_turn_data.items():
            edge = traci.lane.getEdgeID(lane)
            if edge.startswith('N2C') or edge.startswith('S2C'):
                direction_demand['NS'] += len(vehicles)
            else:
                direction_demand['EW'] += len(vehicles)
        
        # Recommend direction with higher right-turn demand
        if direction_demand['NS'] > direction_demand['EW']:
            return 'NS', direction_demand['NS']
        else:
            return 'EW', direction_demand['EW']
    
    def apply_right_turn_optimization(self, current_phase, ns_phase, ew_phase):
        """Apply right-turn optimization logic"""
        if not self.should_optimize_right_turns():
            return current_phase, False
        
        recommended_direction, demand = self.get_optimization_recommendation()
        
        # Switch to recommended direction for right-turn clearance
        if recommended_direction == 'NS' and current_phase != ns_phase:
            print(f"🔄 Right-turn optimization: Switching to NS phase ({demand} right-turn vehicles)")
            return ns_phase, True
        elif recommended_direction == 'EW' and current_phase != ew_phase:
            print(f"🔄 Right-turn optimization: Switching to EW phase ({demand} right-turn vehicles)")
            return ew_phase, True
        
        return current_phase, False

def test_right_turn_optimizer():
    """Test the right-turn optimizer"""
    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Start SUMO
    cmd = ["sumo-gui", "-c", "simulation.sumocfg", "--step-length", "0.1"]
    print("Testing Right-Turn Optimizer...")
    traci.start(cmd)
    
    # Get traffic light info
    tl_id = traci.trafficlight.getIDList()[0]
    controlled_links = traci.trafficlight.getControlledLinks(tl_id)
    lanes = []
    for group in controlled_links:
        for link in group:
            lanes.append(link[0])
    lanes = lanes[:4]
    
    optimizer = RightTurnOptimizer(tl_id, lanes)
    
    # Run simulation with right-turn analysis
    step = 0
    while step < 600:  # 60 seconds
        traci.simulationStep()
        step += 1
        
        # Analyze right turns every 50 steps (5 seconds)
        if step % 50 == 0:
            right_turn_data = optimizer.analyze_right_turns()
            total_right_turns = sum(len(vehicles) for vehicles in right_turn_data.values())
            
            if total_right_turns > 0:
                print(f"[{step*0.1:.1f}s] Right-turn vehicles: {total_right_turns}")
                
                if optimizer.should_optimize_right_turns():
                    direction, demand = optimizer.get_optimization_recommendation()
                    print(f"  🔄 Optimization needed: {direction} direction ({demand} vehicles)")
    
    traci.close()
    print("Right-turn analysis complete!")

if __name__ == "__main__":
    test_right_turn_optimizer()