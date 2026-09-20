#!/usr/bin/env python3
"""
Enhanced RL Traffic Controller with DQN
Builds upon your STDP model with full RL capabilities
"""

import os, sys, math, time, random
import numpy as np
from collections import deque, OrderedDict, defaultdict
import pickle
import json

if "SUMO_HOME" not in os.environ:
    raise SystemExit("Set SUMO_HOME environment variable to your SUMO installation path.")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci
import sumolib

# -------- CONFIG --------
SUMO_BINARY = "sumo-gui"
SUMO_CFG = os.path.join(os.path.dirname(__file__), "simulation.sumocfg")
SUMO_STEP = 0.1
SIM_DURATION = 3600
MIN_GREEN = 15.0  # Increased minimum green time

# RL Parameters
LEARNING_RATE = 0.001
EPSILON_START = 1.0
EPSILON_END = 0.01
EPSILON_DECAY = 0.995
GAMMA = 0.95
BATCH_SIZE = 32
MEMORY_SIZE = 10000
TARGET_UPDATE = 100
SAVE_MODEL_EVERY = 500

class DQNAgent:
    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=MEMORY_SIZE)
        self.epsilon = EPSILON_START
        
        # Neural networks (simplified)
        self.q_network = self._build_network()
        self.target_network = self._build_network()
        self.update_target_network()
        
        self.step_count = 0
        
    def _build_network(self):
        """Simple neural network using numpy"""
        return {
            'W1': np.random.randn(self.state_size, 64) * 0.1,
            'b1': np.zeros(64),
            'W2': np.random.randn(64, 32) * 0.1,
            'b2': np.zeros(32),
            'W3': np.random.randn(32, self.action_size) * 0.1,
            'b3': np.zeros(self.action_size)
        }
    
    def _forward(self, network, state):
        """Forward pass through network"""
        x = np.maximum(0, np.dot(state, network['W1']) + network['b1'])  # ReLU
        x = np.maximum(0, np.dot(x, network['W2']) + network['b2'])      # ReLU
        return np.dot(x, network['W3']) + network['b3']                  # Linear
    
    def act(self, state):
        """Epsilon-greedy action selection"""
        if np.random.random() <= self.epsilon:
            return random.randrange(self.action_size)
        
        q_values = self._forward(self.q_network, state)
        return np.argmax(q_values)
    
    def remember(self, state, action, reward, next_state, done):
        """Store experience in replay buffer"""
        self.memory.append((state, action, reward, next_state, done))
    
    def replay(self):
        """Train the model on a batch of experiences"""
        if len(self.memory) < BATCH_SIZE:
            return
        
        batch = random.sample(self.memory, BATCH_SIZE)
        states = np.array([e[0] for e in batch])
        actions = np.array([e[1] for e in batch])
        rewards = np.array([e[2] for e in batch])
        next_states = np.array([e[3] for e in batch])
        dones = np.array([e[4] for e in batch])
        
        # Current Q values
        current_q = np.array([self._forward(self.q_network, s) for s in states])
        
        # Target Q values
        next_q = np.array([self._forward(self.target_network, s) for s in next_states])
        target_q = current_q.copy()
        
        for i in range(BATCH_SIZE):
            if dones[i]:
                target_q[i][actions[i]] = rewards[i]
            else:
                target_q[i][actions[i]] = rewards[i] + GAMMA * np.max(next_q[i])
        
        # Simple gradient descent update
        self._update_network(states, target_q)
        
        # Decay epsilon
        if self.epsilon > EPSILON_END:
            self.epsilon *= EPSILON_DECAY
    
    def _update_network(self, states, targets):
        """Simple network update using gradient descent"""
        for i in range(len(states)):
            state = states[i]
            target = targets[i]
            
            # Forward pass
            h1 = np.maximum(0, np.dot(state, self.q_network['W1']) + self.q_network['b1'])
            h2 = np.maximum(0, np.dot(h1, self.q_network['W2']) + self.q_network['b2'])
            output = np.dot(h2, self.q_network['W3']) + self.q_network['b3']
            
            # Backward pass (simplified)
            error = target - output
            
            # Update weights (simplified gradient descent)
            self.q_network['W3'] += LEARNING_RATE * np.outer(h2, error)
            self.q_network['b3'] += LEARNING_RATE * error
    
    def update_target_network(self):
        """Copy main network to target network"""
        for key in self.q_network:
            self.target_network[key] = self.q_network[key].copy()

class DynamicRouteOptimizer:
    def __init__(self):
        self.network_edges = []
        self.edge_congestion = {}
        self.alternative_routes = {}
        self.last_optimization = 0
        self.optimization_interval = 30  # 30 seconds
        self.congestion_threshold = 6  # Mixed traffic weight threshold (Indian conditions)
        self.rerouted_vehicles = set()
        
    def initialize_network(self):
        """Initialize network edges and routes"""
        # Get all edges in network
        self.network_edges = ['N2C', 'S2C', 'E2C', 'W2C', 'C2N', 'C2S', 'C2E', 'C2W']
        
        # Simplified route alternatives
        self.alternative_routes = {
            'C2S': ['C2N', 'C2E', 'C2W'],
            'C2N': ['C2S', 'C2E', 'C2W'], 
            'C2E': ['C2W', 'C2N', 'C2S'],
            'C2W': ['C2E', 'C2N', 'C2S']
        }
        
        print("🗺️ Dynamic route optimizer initialized (Indian traffic adapted)")
    
    def monitor_network_congestion(self):
        """Monitor congestion levels - Indian traffic adapted"""
        congestion_data = {}
        
        # Get all vehicles in simulation
        all_vehicles = traci.vehicle.getIDList()
        
        for edge in self.network_edges:
            try:
                # Count vehicles approaching this edge (Indian mixed traffic approach)
                vehicles_on_edge = 0
                mixed_traffic_weight = 0
                
                for veh_id in all_vehicles:
                    try:
                        veh_edge = traci.vehicle.getRoadID(veh_id)
                        if veh_edge == edge:
                            vehicles_on_edge += 1
                            
                            # Indian traffic: different weights for different vehicles
                            veh_type = traci.vehicle.getTypeID(veh_id)
                            if veh_type == 'bus' or veh_type == 'truck':
                                mixed_traffic_weight += 2.0  # Heavy vehicles block more
                            elif veh_type == 'motorcycle' or veh_type == 'auto':
                                mixed_traffic_weight += 0.5  # Light vehicles, less blocking
                            else:
                                mixed_traffic_weight += 1.0  # Cars
                    except:
                        continue
                
                # Indian congestion: consider mixed traffic weight
                congestion_level = mixed_traffic_weight
                
                congestion_data[edge] = {
                    'vehicles': vehicles_on_edge,
                    'congestion': congestion_level,
                    'is_congested': congestion_level > self.congestion_threshold
                }
            except:
                congestion_data[edge] = {'vehicles': 0, 'congestion': 0, 'is_congested': False}
        
        self.edge_congestion = congestion_data
        return congestion_data
    
    def get_alternative_destination(self, current_destination):
        """Get less congested alternative destination"""
        if current_destination not in self.alternative_routes:
            return None
        
        alternatives = self.alternative_routes[current_destination]
        best_dest = None
        min_congestion = float('inf')
        
        # Find least congested alternative
        for dest in alternatives:
            if dest in self.edge_congestion:
                congestion = self.edge_congestion[dest]['congestion']
                if congestion < min_congestion:
                    min_congestion = congestion
                    best_dest = dest
        
        return best_dest
    
    def optimize_routes(self):
        """Main route optimization function"""
        current_time = traci.simulation.getTime()
        
        if current_time - self.last_optimization < self.optimization_interval:
            return
        
        # Monitor network congestion
        congestion_data = self.monitor_network_congestion()
        
        # Find congested edges
        congested_edges = [edge for edge, data in congestion_data.items() if data['is_congested']]
        
        if not congested_edges:
            return
        
        rerouted_count = 0
        
        # Process vehicles on congested edges - Indian traffic approach
        all_vehicles = traci.vehicle.getIDList()
        
        for edge in congested_edges:
            try:
                # Find vehicles on this congested edge
                vehicles_on_edge = []
                for veh_id in all_vehicles:
                    try:
                        if traci.vehicle.getRoadID(veh_id) == edge:
                            vehicles_on_edge.append(veh_id)
                    except:
                        continue
                
                # Indian traffic: prioritize rerouting by vehicle type
                cars_and_autos = [v for v in vehicles_on_edge if traci.vehicle.getTypeID(v) in ['car', 'auto']]
                
                for veh_id in cars_and_autos[:2]:  # Reroute 2 cars/autos (easier to reroute)
                    if veh_id in self.rerouted_vehicles:
                        continue
                    
                    try:
                        current_route = traci.vehicle.getRoute(veh_id)
                        if len(current_route) < 2:
                            continue
                        
                        veh_type = traci.vehicle.getTypeID(veh_id)
                        current_dest = current_route[-1]
                        
                        # Indian traffic: smart rerouting based on vehicle type
                        if veh_type == 'auto':  # Autos are flexible, can take any route
                            alternatives = ['C2N', 'C2S', 'C2E', 'C2W']
                        else:  # Cars prefer main routes
                            alternatives = ['C2N', 'C2S'] if current_dest in ['C2E', 'C2W'] else ['C2E', 'C2W']
                        
                        # Pick least congested alternative
                        best_dest = None
                        min_congestion = float('inf')
                        
                        for dest in alternatives:
                            if dest != current_dest and dest in self.edge_congestion:
                                dest_congestion = self.edge_congestion[dest]['congestion']
                                if dest_congestion < min_congestion:
                                    min_congestion = dest_congestion
                                    best_dest = dest
                        
                        if best_dest:
                            try:
                                new_route = [current_route[0], best_dest]
                                traci.vehicle.setRoute(veh_id, new_route)
                                self.rerouted_vehicles.add(veh_id)
                                rerouted_count += 1
                                print(f"🗺️ [{current_time:.0f}s] Rerouted {veh_type} {veh_id}: {current_dest}→{best_dest} (Indian traffic)")
                            except:
                                continue
                    
                    except:
                        continue
            
            except:
                continue
        
        if rerouted_count > 0:
            total_congested = len(congested_edges)
            print(f"🗺️ [{current_time:.0f}s] Network optimization: {rerouted_count} vehicles rerouted, {total_congested} congested edges")
        
        self.last_optimization = current_time
    
    def get_network_status(self):
        """Get current network congestion status"""
        if not self.edge_congestion:
            return "Unknown"
        
        total_vehicles = sum(data['vehicles'] for data in self.edge_congestion.values())
        congested_edges = sum(1 for data in self.edge_congestion.values() if data['is_congested'])
        
        if congested_edges == 0:
            return "Optimal"
        elif congested_edges <= 2:
            return "Moderate"
        else:
            return "Congested"

class PredictiveAnalytics:
    def __init__(self):
        self.historical_data = defaultdict(list)
        self.patterns = {}
        self.time_slot_size = 300  # 5 minutes
        self.last_prediction = 0
        
    def collect_data(self, lanes):
        """Collect traffic data for pattern learning"""
        current_time = traci.simulation.getTime()
        time_slot = int(current_time // self.time_slot_size)
        
        queues = [traci.lane.getLastStepVehicleNumber(l) for l in lanes]
        waiting_times = [traci.lane.getWaitingTime(l) for l in lanes]
        
        data = {
            'time': current_time,
            'total_vehicles': sum(queues),
            'avg_waiting': np.mean(waiting_times),
            'congestion_level': min(sum(queues) * 5 + np.mean(waiting_times), 100)
        }
        
        self.historical_data[time_slot].append(data)
        return data
    
    def learn_patterns(self):
        """Learn traffic patterns"""
        for time_slot, data_list in self.historical_data.items():
            if len(data_list) > 0:
                avg_vehicles = np.mean([d['total_vehicles'] for d in data_list])
                avg_waiting = np.mean([d['avg_waiting'] for d in data_list])
                congestion = np.mean([d['congestion_level'] for d in data_list])
                
                self.patterns[time_slot] = {
                    'vehicles': avg_vehicles,
                    'waiting': avg_waiting,
                    'congestion': congestion
                }
    
    def predict_traffic(self):
        """Predict next 15 minutes traffic"""
        current_time = traci.simulation.getTime()
        current_slot = int(current_time // self.time_slot_size)
        
        predictions = []
        for i in range(1, 4):  # Next 3 slots (15 minutes)
            future_slot = current_slot + i
            if future_slot in self.patterns:
                pattern = self.patterns[future_slot]
                predictions.append({
                    'time_ahead': i * 5,
                    'congestion': pattern['congestion'],
                    'vehicles': pattern['vehicles']
                })
        
        return predictions
    
    def get_strategy(self, predictions):
        """Get optimization strategy based on predictions"""
        if not predictions:
            return "maintain", 10.0
        
        avg_congestion = np.mean([p['congestion'] for p in predictions])
        
        if avg_congestion > 70:
            return "aggressive", 6.0  # Faster decisions
        elif avg_congestion > 40:
            return "moderate", 8.0
        else:
            return "relaxed", 12.0

class TrafficEnvironment:
    def __init__(self):
        self.tl_id = None
        self.lanes = []
        self.edges = []
        self.ns_phase = 0
        self.ew_phase = 1
        self.current_phase = 0
        self.last_change = 0
        self.last_decision = 0
        self.decision_interval = 10.0  # Make decisions every 10 seconds
        self.prev_waiting_times = []
        self.emergency_override = False
        self.emergency_start_time = 0
        self.emergency_types = ['ambulance', 'fire_truck', 'police']
        self.right_turn_optimizer = None
        self.predictive_analytics = PredictiveAnalytics()
        self.route_optimizer = DynamicRouteOptimizer()
        
    def start_sumo(self):
        # Change to script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        sumo_binary = os.path.join(os.environ.get("SUMO_HOME", "C:\\Program Files (x86)\\Eclipse\\Sumo"), "bin", "sumo-gui.exe")
        cmd = [sumo_binary, "-c", "simulation.sumocfg", "--step-length", str(SUMO_STEP)]
        print("Starting SUMO:", " ".join(cmd))
        print("Working directory:", os.getcwd())
        traci.start(cmd)
        
    def setup_intersection(self):
        """Setup intersection detection (from your original code)"""
        tls = traci.trafficlight.getIDList()
        if not tls:
            raise SystemExit("No traffic lights found")
        
        self.tl_id = tls[0]
        controlled_links = traci.trafficlight.getControlledLinks(self.tl_id)
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
        self.lanes = [edge_to_lanes[e][0] for e in selected_edges]
        self.edges = selected_edges
        
        # Auto-detect phases (from your original code)
        net_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network.net.xml")
        net = sumolib.net.readNet(net_file)
        directions = self._classify_directions(net, selected_edges)
        self.ns_phase, self.ew_phase = self._auto_map_phases(directions, from_lanes)
        
        # Initialize right-turn optimizer
        from right_turn_optimizer import RightTurnOptimizer
        self.right_turn_optimizer = RightTurnOptimizer(self.tl_id, self.lanes)
        
        # Initialize route optimizer
        self.route_optimizer.initialize_network()
        
        print(f"Setup complete: {len(self.lanes)} lanes, NS phase: {self.ns_phase}, EW phase: {self.ew_phase}")
        print("🔄 Right-turn optimizer initialized")
        print("🔮 Predictive analytics initialized")
        print("🗺️ Dynamic route optimization active")
    
    def _classify_directions(self, net, edges):
        """From your original code"""
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
    
    def _auto_map_phases(self, directions, from_lanes):
        """From your original code"""
        lane_groups = []
        for lane in from_lanes:
            e = traci.lane.getEdgeID(lane)
            d = directions.get(e, None)
            grp = 'NS' if d in ('N','S') else 'EW'
            lane_groups.append(grp)

        defs = traci.trafficlight.getCompleteRedYellowGreenDefinition(self.tl_id)
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
        
        return int(np.argmax(ns_counts)), int(np.argmax(ew_counts))
    
    def get_state(self):
        """Enhanced state representation with right-turn info"""
        # Queue lengths
        queues = [traci.lane.getLastStepVehicleNumber(l) for l in self.lanes]
        
        # Waiting times
        waiting_times = [traci.lane.getWaitingTime(l) for l in self.lanes]
        
        # Right-turn vehicle counts (vehicles wanting to turn right)
        right_turn_counts = []
        for lane in self.lanes:
            right_turn_vehicles = 0
            for veh_id in traci.lane.getLastStepVehicleIDs(lane):
                try:
                    route = traci.vehicle.getRoute(veh_id)
                    current_edge = traci.vehicle.getRoadID(veh_id)
                    if len(route) > 1:
                        next_edge = route[route.index(current_edge) + 1] if current_edge in route else None
                        # Check if it's a right turn based on edge names
                        if self._is_right_turn(current_edge, next_edge):
                            right_turn_vehicles += 1
                except:
                    continue
            right_turn_counts.append(right_turn_vehicles)
        
        # Current phase info
        current_phase = traci.trafficlight.getPhase(self.tl_id)
        phase_duration = traci.simulation.getTime() - self.last_change
        
        # Normalize features
        state = np.array(queues + waiting_times + right_turn_counts + [current_phase, phase_duration])
        return state / (np.max(state) + 1e-6)  # Normalize
    
    def _is_right_turn(self, from_edge, to_edge):
        """Check if movement is a right turn"""
        if not from_edge or not to_edge:
            return False
        
        # Define right turn patterns
        right_turns = {
            'N2C': 'C2E',  # North to East
            'E2C': 'C2S',  # East to South  
            'S2C': 'C2W',  # South to West
            'W2C': 'C2N'   # West to North
        }
        
        return right_turns.get(from_edge) == to_edge
    
    def calculate_reward(self):
        """Enhanced reward function with right-turn optimization"""
        # Current metrics
        queues = [traci.lane.getLastStepVehicleNumber(l) for l in self.lanes]
        waiting_times = [traci.lane.getWaitingTime(l) for l in self.lanes]
        
        # Multi-objective reward
        queue_penalty = -sum(queues) * 0.1
        waiting_penalty = -sum(waiting_times) * 0.01
        
        # Throughput reward
        total_vehicles = sum([traci.lane.getLastStepVehicleNumber(l) for l in self.lanes])
        throughput_reward = total_vehicles * 0.05
        
        # Fairness reward (balance between directions)
        ns_load = sum(queues[:2]) if len(queues) >= 2 else 0
        ew_load = sum(queues[2:]) if len(queues) >= 4 else 0
        fairness_penalty = -abs(ns_load - ew_load) * 0.02
        
        # Right-turn penalty (heavy penalty for blocking right turns)
        right_turn_penalty = 0
        for lane in self.lanes:
            for veh_id in traci.lane.getLastStepVehicleIDs(lane):
                try:
                    route = traci.vehicle.getRoute(veh_id)
                    current_edge = traci.vehicle.getRoadID(veh_id)
                    if len(route) > 1:
                        next_edge = route[route.index(current_edge) + 1] if current_edge in route else None
                        if self._is_right_turn(current_edge, next_edge):
                            wait_time = traci.vehicle.getWaitingTime(veh_id)
                            if wait_time > 10:  # Right-turn vehicle waiting > 10s
                                right_turn_penalty -= wait_time * 0.05  # Heavy penalty
                except:
                    continue
        
        # Emergency vehicle bonus
        emergency_bonus = 0
        if self.emergency_override:
            emergency_bonus = 10.0  # High reward for handling emergency
        
        return queue_penalty + waiting_penalty + throughput_reward + fairness_penalty + right_turn_penalty + emergency_bonus
    
    def detect_emergency_vehicles(self):
        """Detect emergency vehicles near intersection"""
        emergency_vehicles = []
        for veh_id in traci.vehicle.getIDList():
            veh_type = traci.vehicle.getTypeID(veh_id)
            if veh_type in self.emergency_types:
                try:
                    lane_id = traci.vehicle.getLaneID(veh_id)
                    edge_id = traci.lane.getEdgeID(lane_id)
                    # Check if on any incoming edge (not just monitored lanes)
                    if any(edge_id.startswith(prefix) for prefix in ['N2C', 'S2C', 'E2C', 'W2C']):
                        distance = traci.vehicle.getLanePosition(veh_id)
                        lane_length = traci.lane.getLength(lane_id)
                        # Emergency vehicle within 150m of intersection
                        if lane_length - distance < 150:
                            emergency_vehicles.append((veh_id, veh_type, edge_id))
                            print(f"🚨 Emergency detected: {veh_type} {veh_id} on {edge_id} at {distance:.1f}m")
                except Exception as e:
                    print(f"Detection error for {veh_id}: {e}")
                    continue
        return emergency_vehicles
    
    def get_emergency_phase(self, emergency_edge):
        """Get required phase for emergency vehicle direction"""
        # Map edge to direction based on edge name
        if emergency_edge.startswith('N2C') or emergency_edge.startswith('S2C'):
            return self.ns_phase  # North-South phase
        else:
            return self.ew_phase  # East-West phase
    
    def step(self, action):
        """Execute action and return next state, reward, done"""
        current_time = traci.simulation.getTime()
        
        # Check for emergency vehicles
        emergency_vehicles = self.detect_emergency_vehicles()
        
        if emergency_vehicles:
            # Emergency override - IMMEDIATE ACTION
            if not self.emergency_override:
                self.emergency_override = True
                self.emergency_start_time = current_time
                print(f"🚨 [{current_time:.1f}s] EMERGENCY OVERRIDE ACTIVATED - {len(emergency_vehicles)} vehicles")
            
            # Get emergency phase and switch IMMEDIATELY
            emergency_edge = emergency_vehicles[0][2]
            emergency_phase = self.get_emergency_phase(emergency_edge)
            veh_id = emergency_vehicles[0][0]
            veh_type = emergency_vehicles[0][1]
            
            # FORCE immediate phase change for emergency
            if emergency_phase != self.current_phase:
                traci.trafficlight.setPhase(self.tl_id, emergency_phase)
                self.current_phase = emergency_phase
                self.last_change = current_time
                print(f"🚨 [{current_time:.1f}s] IMMEDIATE phase {emergency_phase} for {veh_type} {veh_id}")
            else:
                print(f"🚨 [{current_time:.1f}s] Emergency phase {emergency_phase} already active for {veh_type}")
        
        elif self.emergency_override:
            # End emergency override after 15 seconds
            if current_time - self.emergency_start_time > 15:
                self.emergency_override = False
                print(f"✅ [{current_time:.1f}s] Emergency override ended, resuming RL control")
        
        # Normal RL control with right-turn optimization (only if no emergency)
        if not self.emergency_override:
            if current_time - self.last_decision >= self.decision_interval:
                target_phase = self.ns_phase if action == 0 else self.ew_phase
                time_since_change = current_time - self.last_change
                
                # Check for right-turn optimization
                optimized_phase, was_optimized = self.right_turn_optimizer.apply_right_turn_optimization(
                    self.current_phase, self.ns_phase, self.ew_phase)
                
                # Use optimized phase if available, otherwise use RL decision
                final_phase = optimized_phase if was_optimized else target_phase
                
                if final_phase != self.current_phase and time_since_change >= MIN_GREEN:
                    traci.trafficlight.setPhase(self.tl_id, final_phase)
                    self.current_phase = final_phase
                    self.last_change = current_time
                    
                    if was_optimized:
                        print(f"[{current_time:.1f}s] Right-turn optimized phase change to {final_phase}")
                    else:
                        print(f"[{current_time:.1f}s] RL phase change to {final_phase}")
                
                self.last_decision = current_time
        
        # Predictive Analytics
        traffic_data = self.predictive_analytics.collect_data(self.lanes)
        
        # Learn patterns every minute
        if int(current_time) % 60 == 0:
            self.predictive_analytics.learn_patterns()
        
        # Make predictions every 5 minutes
        if current_time - self.predictive_analytics.last_prediction >= 300:
            predictions = self.predictive_analytics.predict_traffic()
            if predictions:
                strategy, new_interval = self.predictive_analytics.get_strategy(predictions)
                if new_interval != self.decision_interval:
                    self.decision_interval = new_interval
                    print(f"🔮 [{current_time:.0f}s] Strategy: {strategy}, Interval: {new_interval}s")
                    print(f"   Predictions: {[f'+{p["time_ahead"]}min: {p["congestion"]:.0f}%' for p in predictions[:2]]}")
            self.predictive_analytics.last_prediction = current_time
        
        # Dynamic Route Optimization
        self.route_optimizer.optimize_routes()
        
        # Step simulation
        traci.simulationStep()
        
        # --- Write screenshot ---
        try:
            if self.view_id:
                traci.gui.screenshot(self.view_id, os.path.join(os.path.dirname(__file__), "latest_screenshot.jpg"))
        except Exception:
            pass

        # --- Write signal states JSON ---
        try:
            states = {}
            tls = traci.trafficlight.getIDList()
            for i, tl_id in enumerate(tls[:4]):  # A, B, C, D
                current_phase = traci.trafficlight.getPhase(tl_id)
                states[chr(65 + i)] = {"phase": str(current_phase)}
            with open(os.path.join(os.path.dirname(__file__), "signal_states.json"), "w") as f:
                json.dump(states, f)
        except Exception as e:
            print(f"Signal state write error: {e}")

        
        # Get reward and next state
        reward = self.calculate_reward()
        next_state = self.get_state()
        done = traci.simulation.getTime() >= SIM_DURATION
        
        return next_state, reward, done

def train_rl_controller():
    """Main training loop"""
    env = TrafficEnvironment()
    env.start_sumo()
    env.setup_intersection()
    
    state_size = len(env.lanes) * 3 + 2  # queues + waiting_times + right_turns + phase + duration
    action_size = 2  # NS or EW
    agent = DQNAgent(state_size, action_size)
    
    # Load existing patterns if available
    patterns_path = os.path.join('saved_models', 'traffic_patterns.pkl')
    try:
        with open(patterns_path, 'rb') as f:
            env.predictive_analytics.patterns = pickle.load(f)
        print(f"📁 Loaded {len(env.predictive_analytics.patterns)} traffic patterns from saved_models/")
    except:
        print("🆕 No existing patterns found, starting fresh")
    
    print(f"🚀 Starting RL Training - State size: {state_size}, Actions: {action_size}")
    print("🔮 Predictive analytics active")
    
    episode = 0
    total_reward = 0
    state = env.get_state()
    
    print("🔮 Predictive Analytics Features:")
    print("  - Learns traffic patterns every 5 minutes")
    print("  - Predicts congestion 15 minutes ahead")
    print("  - Adapts decision timing: 6s (aggressive) to 12s (relaxed)")
    print("  - Saves/loads patterns for continuous learning")
    
    print("🗺️ Dynamic Route Optimization Features:")
    print("  - Monitors network congestion every 30 seconds")
    print("  - Reroutes vehicles to avoid traffic jams")
    print("  - Balances load across alternative routes")
    print("  - Prevents cascade congestion effects")
    
    while traci.simulation.getTime() < SIM_DURATION:
        # Choose action (timing controlled by predictive analytics)
        action = agent.act(state)
        
        # Execute action
        next_state, reward, done = env.step(action)
        
        # Store experience
        agent.remember(state, action, reward, next_state, done)
        
        # Train agent
        agent.replay()
        
        # Update target network
        agent.step_count += 1
        if agent.step_count % TARGET_UPDATE == 0:
            agent.update_target_network()
            patterns_count = len(env.predictive_analytics.patterns)
            network_status = env.route_optimizer.get_network_status()
            rerouted_count = len(env.route_optimizer.rerouted_vehicles)
            print(f"🎯 Target network updated at step {agent.step_count} (patterns: {patterns_count}, network: {network_status}, rerouted: {rerouted_count})")
        
        # Save model
        if agent.step_count % SAVE_MODEL_EVERY == 0:
            models_dir = 'saved_models'
            os.makedirs(models_dir, exist_ok=True)
            with open(os.path.join(models_dir, f'rl_model_step_{agent.step_count}.pkl'), 'wb') as f:
                pickle.dump(agent.q_network, f)
            # Save patterns too
            with open(os.path.join(models_dir, 'traffic_patterns.pkl'), 'wb') as f:
                pickle.dump(env.predictive_analytics.patterns, f)
            print(f"💾 Model and patterns saved to saved_models/ at step {agent.step_count}")
        
        state = next_state
        total_reward += reward
        
        if done:
            break
    
    # Save predictive patterns
    try:
        models_dir = 'saved_models'
        os.makedirs(models_dir, exist_ok=True)
        with open(os.path.join(models_dir, 'traffic_patterns.pkl'), 'wb') as f:
            pickle.dump(env.predictive_analytics.patterns, f)
        print("💾 Predictive patterns saved to saved_models/")
    except:
        pass
    
    traci.close()
    
    print(f"\n🎉 Training Complete!")
    print(f"Total steps: {agent.step_count}")
    print(f"Total reward: {total_reward:.2f}")
    print(f"Final epsilon: {agent.epsilon:.3f}")
    print(f"Memory size: {len(agent.memory)}")
    print(f"Learned patterns: {len(env.predictive_analytics.patterns)} time slots")
    print(f"Network optimization: {len(env.route_optimizer.rerouted_vehicles)} vehicles rerouted")
    print(f"Final network status: {env.route_optimizer.get_network_status()}")

if __name__ == "__main__":
    train_rl_controller()