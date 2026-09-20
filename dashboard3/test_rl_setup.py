#!/usr/bin/env python3
"""
Test RL setup - verify files and SUMO connection
"""

import os, sys

# Check SUMO_HOME
if "SUMO_HOME" not in os.environ:
    print("[X] SUMO_HOME not set")
    sys.exit(1)

print("[OK] SUMO_HOME:", os.environ["SUMO_HOME"])

# Add SUMO tools
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

try:
    import traci
    import sumolib
    print("[OK] SUMO tools imported")
except ImportError as e:
    print("[X] SUMO import failed:", e)
    sys.exit(1)

# Check files
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

files = ["simulation.sumocfg", "network.net.xml", "routes.rou.xml"]
for f in files:
    if os.path.exists(f):
        print(f"[OK] {f} found")
    else:
        print(f"[X] {f} missing")

# Test SUMO start
try:
    cmd = ["sumo", "-c", "simulation.sumocfg", "--step-length", "0.1"]
    print("\nTesting SUMO connection...")
    traci.start(cmd)
    
    # Quick test
    tls = traci.trafficlight.getIDList()
    print(f"[OK] Found {len(tls)} traffic lights: {tls}")
    
    traci.close()
    print("[OK] SUMO test successful!")
    
except Exception as e:
    print(f"[X] SUMO test failed: {e}")

print("\nSetup verification complete. Run: python enhanced_rl_controller.py")