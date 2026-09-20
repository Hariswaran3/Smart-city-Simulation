#!/usr/bin/env python3
"""
Live SUMO Dashboard with Real-time Traffic Light Status
Integrates SUMO simulation streaming with traffic signal monitoring
"""

import os
import sys
import json
import time
import threading
import cv2
import numpy as np
from flask import Flask, render_template, jsonify, Response
from flask_cors import CORS

# SUMO setup
if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    sys.path.append(tools)
else:
    raise EnvironmentError("Please set SUMO_HOME environment variable")

import traci
import subprocess

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

class SUMODashboard:
    def __init__(self):
        self.sumo_process = None
        self.view_id = None
        self.latest_frame = None
        self.signal_states = {}
        self.simulation_running = False
        self.screenshot_path = "latest_screenshot.jpg"
        
    def start_sumo(self):
        """Start SUMO simulation"""
        try:
            # Start SUMO-GUI with better settings for screenshots
            sumo_binary = os.path.join(os.environ.get("SUMO_HOME", ""), "bin", "sumo-gui.exe")
            if not os.path.exists(sumo_binary):
                sumo_binary = "sumo-gui" # fallback
                
            sumo_cmd = [
                sumo_binary,
                "-c", "simulation.sumocfg",
                "--start",
                "--step-length", "0.1",
                "--remote-port", "8813",
                "--gui-settings-file", "gui-settings.xml"
            ]
            
            # Create GUI settings for better visibility
            gui_settings = '''<?xml version="1.0" encoding="UTF-8"?>
<viewsettings>
    <scheme name="real world"/>
    <delay value="100"/>
    <viewport zoom="2000" x="200" y="200" angle="0"/>
</viewsettings>'''
            
            with open('gui-settings.xml', 'w') as f:
                f.write(gui_settings)
            
            print("Starting SUMO:", " ".join(sumo_cmd[:-2]))  # Don't show gui-settings in log
            self.sumo_process = subprocess.Popen(sumo_cmd)
            time.sleep(3)  # Wait longer for SUMO to start
            
            # Connect to TraCI
            traci.init(8813)
            
            # Get view ID for screenshots
            views = traci.gui.getIDList()
            if views:
                self.view_id = views[0]
                print(f"Using SUMO view: {self.view_id}")
                
                # Set view to show the network properly
                traci.gui.setZoom(self.view_id, 2000)
                traci.gui.setOffset(self.view_id, 200, 200)
            else:
                print("⚠️ No SUMO views found")
            
            self.simulation_running = True
            print("✅ SUMO connected successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start SUMO: {e}")
            return False
    
    def capture_frame(self):
        """Capture screenshot from SUMO"""
        if not self.simulation_running:
            return None
            
        try:
            # Get view ID if not set
            if not self.view_id:
                views = traci.gui.getIDList()
                if views:
                    self.view_id = views[0]
                    print(f"Using SUMO view: {self.view_id}")
                else:
                    print("No SUMO views available")
                    return None
            
            # Use absolute path for screenshot
            screenshot_path = os.path.abspath(self.screenshot_path)
            
            # Take screenshot
            traci.gui.screenshot(self.view_id, screenshot_path)
            
            # Wait a moment for file to be written
            time.sleep(0.01)
            
            # Check if file exists and has content
            if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                # Read and encode image
                frame = cv2.imread(screenshot_path)
                if frame is not None and frame.size > 0:
                    # Resize for better streaming performance
                    frame = cv2.resize(frame, (800, 600))
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    self.latest_frame = buffer.tobytes()
                    print(f"Frame captured: {frame.shape}")
                    return self.latest_frame
                else:
                    print(f"Failed to read image from {screenshot_path}")
            else:
                print(f"Screenshot file not created or empty: {screenshot_path}")
                
        except Exception as e:
            print(f"Frame capture error: {e}")
            
        return None
    
    def get_traffic_light_states(self):
        """Get current traffic light states"""
        if not self.simulation_running:
            return {}
            
        try:
            tls = traci.trafficlight.getIDList()
            states = {}
            
            print(f"Found {len(tls)} traffic lights: {tls}")
            
            if not tls:
                print("⚠️ No traffic lights found in simulation")
                return {}
            
            # Process only actual traffic lights from SUMO
            for i, tl_id in enumerate(tls):
                try:
                    current_phase = traci.trafficlight.getPhase(tl_id)
                    phase_state = traci.trafficlight.getRedYellowGreenState(tl_id)
                    
                    print(f"TL {tl_id}: Phase {current_phase}, State: {phase_state}")
                    
                    # Determine dominant signal state
                    green_count = phase_state.count('G') + phase_state.count('g')
                    red_count = phase_state.count('r') + phase_state.count('R')
                    yellow_count = phase_state.count('y') + phase_state.count('Y')
                    
                    # Priority: Green > Yellow > Red
                    if green_count > 0:
                        red, yellow, green = False, False, True
                    elif yellow_count > 0:
                        red, yellow, green = False, True, False
                    else:
                        red, yellow, green = True, False, False
                    
                    intersection_name = chr(65 + i)  # A, B, C, D...
                    states[intersection_name] = {
                        "phase": current_phase,
                        "state": phase_state,
                        "red": red,
                        "yellow": yellow,
                        "green": green,
                        "lanes": self.get_lane_info(tl_id)
                    }
                    
                except Exception as e:
                    print(f"Error reading TL {tl_id}: {e}")
                    continue
            
            self.signal_states = states
            return states
            
        except Exception as e:
            print(f"Traffic light state error: {e}")
            return {}
    
    def get_lane_info(self, tl_id):
        """Get exact current traffic light state from SUMO"""
        try:
            # Get the EXACT current state from SUMO
            phase_state = traci.trafficlight.getRedYellowGreenState(tl_id)
            current_phase = traci.trafficlight.getPhase(tl_id)
            controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
            
            print(f"EXACT TL {tl_id}: Phase {current_phase}, State: {phase_state}")
            
            # Read the actual signal state directly from SUMO's current phase
            # Based on your network.net.xml: "GGGgrrrrGGGgrrrr" pattern
            # First 8 chars = NS directions, Last 8 chars = EW directions
            
            ns_signal = "red"
            ew_signal = "red"
            
            if len(phase_state) >= 8:
                # Check NS signals (first half)
                ns_chars = phase_state[:8]
                if 'G' in ns_chars or 'g' in ns_chars:
                    ns_signal = "green"
                elif 'y' in ns_chars or 'Y' in ns_chars:
                    ns_signal = "yellow"
                
                # Check EW signals (second half)
                ew_chars = phase_state[8:] if len(phase_state) > 8 else phase_state
                if 'G' in ew_chars or 'g' in ew_chars:
                    ew_signal = "green"
                elif 'y' in ew_chars or 'Y' in ew_chars:
                    ew_signal = "yellow"
            
            # Get real lane data
            lane_data = {}
            for lane in controlled_lanes:
                try:
                    direction = self.get_lane_direction(lane)
                    if direction != "Unknown":
                        vehicles = traci.lane.getLastStepVehicleNumber(lane)
                        waiting_time = traci.lane.getWaitingTime(lane)
                        
                        if direction in lane_data:
                            lane_data[direction]["vehicles"] += vehicles
                            lane_data[direction]["waiting_time"] = max(
                                lane_data[direction]["waiting_time"], waiting_time
                            )
                        else:
                            lane_data[direction] = {
                                "vehicles": vehicles,
                                "waiting_time": round(waiting_time, 1)
                            }
                except Exception:
                    continue
            
            # Build final lane info with EXACT signals
            lane_info = {}
            for direction in ["North", "South", "East", "West"]:
                # Use exact signal from SUMO
                if direction in ["North", "South"]:
                    signal = ns_signal
                else:
                    signal = ew_signal
                
                data = lane_data.get(direction, {"vehicles": 0, "waiting_time": 0.0})
                
                lane_info[direction] = {
                    "vehicles": data["vehicles"],
                    "waiting_time": data["waiting_time"],
                    "signal": signal
                }
            
            print(f"SIGNALS - NS: {ns_signal}, EW: {ew_signal}")
            return lane_info
            
        except Exception as e:
            print(f"Lane info error: {e}")
            return self.get_dummy_lane_info()
    
    def get_lane_direction(self, lane_id):
        """Determine lane direction from ID"""
        lane_lower = lane_id.lower()
        
        # Check various naming patterns
        if any(x in lane_lower for x in ['n2c', 'north', '_n_', 'from_n']):
            return "North"
        elif any(x in lane_lower for x in ['s2c', 'south', '_s_', 'from_s']):
            return "South"
        elif any(x in lane_lower for x in ['e2c', 'east', '_e_', 'from_e']):
            return "East"
        elif any(x in lane_lower for x in ['w2c', 'west', '_w_', 'from_w']):
            return "West"
        
        # Try to get edge and determine from coordinates
        try:
            edge_id = traci.lane.getEdgeID(lane_id)
            return self.get_edge_direction(edge_id)
        except:
            return "Unknown"
    
    def get_edge_direction(self, edge_id):
        """Get direction from edge geometry"""
        try:
            # This is a simplified approach
            edge_lower = edge_id.lower()
            if any(x in edge_lower for x in ['north', 'n', 'top']):
                return "North"
            elif any(x in edge_lower for x in ['south', 's', 'bottom']):
                return "South"
            elif any(x in edge_lower for x in ['east', 'e', 'right']):
                return "East"
            elif any(x in edge_lower for x in ['west', 'w', 'left']):
                return "West"
        except:
            pass
        return "Unknown"
    
    def get_dummy_lane_info(self):
        """Get dummy lane info for display"""
        return {
            "North": {"vehicles": 0, "waiting_time": 0.0, "signal": "red"},
            "South": {"vehicles": 0, "waiting_time": 0.0, "signal": "red"},
            "East": {"vehicles": 0, "waiting_time": 0.0, "signal": "red"},
            "West": {"vehicles": 0, "waiting_time": 0.0, "signal": "red"}
        }
    

    
    def step_simulation(self):
        """Advance simulation by one step"""
        if self.simulation_running:
            try:
                traci.simulationStep()
                return True
            except Exception as e:
                print(f"Simulation step error: {e}")
                return False
        return False
    
    def stop_sumo(self):
        """Stop SUMO simulation"""
        try:
            if self.simulation_running:
                traci.close()
                self.simulation_running = False
            
            if self.sumo_process:
                self.sumo_process.terminate()
                self.sumo_process.wait()
                
            print("✅ SUMO stopped")
            
        except Exception as e:
            print(f"Error stopping SUMO: {e}")

# Global dashboard instance
dashboard = SUMODashboard()

def simulation_loop():
    """Background thread for simulation"""
    step_count = 0
    while dashboard.simulation_running:
        try:
            # Step simulation FIRST
            if not dashboard.step_simulation():
                break
            
            # WAIT for SUMO to process the step completely
            time.sleep(0.05)
                
            # Update traffic light states AFTER simulation step
            states = dashboard.get_traffic_light_states()
                
            # Capture frame for video stream
            if step_count % 3 == 0:
                dashboard.capture_frame()
                
            if step_count % 50 == 0:  # Debug every 50 steps
                print(f"Step {step_count}: Intersections: {len(states)}, Video: {'Yes' if dashboard.latest_frame else 'No'}")
            
            step_count += 1
            
            # Control simulation speed
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Simulation loop error: {e}")
            break

@app.route("/")
def index():
    """Serve dashboard HTML"""
    return render_template("dash_board.html")

@app.route("/live")
def live_feed():
    """Stream live SUMO feed"""
    def generate():
        while True:
            try:
                if dashboard.latest_frame and dashboard.simulation_running:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + dashboard.latest_frame + b'\r\n')
                else:
                    # Placeholder frame if no feed
                    img = np.zeros((600, 800, 3), dtype=np.uint8)
                    if dashboard.simulation_running:
                        cv2.putText(img, "SUMO Simulation", (250, 280),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                        cv2.putText(img, "Loading...", (320, 320),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    else:
                        cv2.putText(img, "Click Start to Begin", (220, 280),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                        cv2.putText(img, "Simulation", (320, 320),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    
                    _, buffer = cv2.imencode('.jpg', img)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                
                time.sleep(0.1)  # ~10 FPS
                
            except GeneratorExit:
                break
            except Exception as e:
                print(f"Live feed error: {e}")
                time.sleep(0.5)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/status")
def api_status():
    """Get current simulation status and traffic light states"""
    try:
        # Get fresh traffic light states
        traffic_states = dashboard.get_traffic_light_states()
        
        # Calculate overall metrics
        total_vehicles = 0
        total_waiting = 0
        congested_intersections = 0
        
        for intersection, data in traffic_states.items():
            lanes = data.get("lanes", {})
            for direction, lane_data in lanes.items():
                total_vehicles += lane_data.get("vehicles", 0)
                total_waiting += lane_data.get("waiting_time", 0)
                
            # Check if intersection is congested
            if any(lane.get("waiting_time", 0) > 30 for lane in lanes.values()):
                congested_intersections += 1
        
        # Determine overall status
        if congested_intersections > 2:
            flow_status = "Heavy Traffic"
            system_status = "Congested"
        elif congested_intersections > 0:
            flow_status = "Moderate Traffic"
            system_status = "Normal"
        else:
            flow_status = "Light Traffic"
            system_status = "Optimal"
        
        return jsonify({
            "simulation_running": dashboard.simulation_running,
            "intersections": traffic_states,
            "mode": "RL Control" if dashboard.simulation_running else "Stopped",
            "phase": "Adaptive",
            "flow": flow_status,
            "status": system_status,
            "emergency": "Inactive",
            "metrics": {
                "total_vehicles": total_vehicles,
                "avg_waiting_time": round(total_waiting / max(len(traffic_states), 1), 1),
                "congested_intersections": congested_intersections,
                "throughput": total_vehicles * 2  # Approximate throughput
            }
        })
        
    except Exception as e:
        print(f"Status API error: {e}")
        return jsonify({
            "simulation_running": False,
            "intersections": {},
            "mode": "Error",
            "phase": "Unknown",
            "flow": "Unknown",
            "status": "Error",
            "emergency": "Unknown"
        })

@app.route("/api/control", methods=["POST"])
def api_control():
    """Handle control commands"""
    try:
        from flask import request
        data = request.get_json()
        action = data.get("action", "")
        
        if action == "start" and not dashboard.simulation_running:
            if dashboard.start_sumo():
                # Start simulation thread
                threading.Thread(target=simulation_loop, daemon=True).start()
                return jsonify({"success": True, "message": "Simulation started"})
            else:
                return jsonify({"success": False, "message": "Failed to start SUMO"})
                
        elif action == "stop" and dashboard.simulation_running:
            dashboard.stop_sumo()
            return jsonify({"success": True, "message": "Simulation stopped"})
            
        elif action == "reset":
            dashboard.stop_sumo()
            time.sleep(1)
            if dashboard.start_sumo():
                threading.Thread(target=simulation_loop, daemon=True).start()
                return jsonify({"success": True, "message": "Simulation reset"})
            else:
                return jsonify({"success": False, "message": "Failed to reset"})
        
        else:
            return jsonify({"success": False, "message": f"Unknown action: {action}"})
            
    except Exception as e:
        print(f"Control API error: {e}")
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    print("🚦 Starting SUMO Live Dashboard")
    print("📺 Dashboard will be available at http://localhost:5000")
    print("🎮 Use the web interface to start/stop simulation")
    
    # Auto-start SUMO if config exists
    if os.path.exists("simulation.sumocfg"):
        print("🚀 Auto-starting SUMO simulation...")
        if dashboard.start_sumo():
            threading.Thread(target=simulation_loop, daemon=True).start()
            print("✅ SUMO simulation started automatically")
        else:
            print("⚠️ Auto-start failed, use web interface to start manually")
    
    try:
        app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
    finally:
        dashboard.stop_sumo()