#!/usr/bin/env python3
"""
test_setup.py - Quick SUMO setup verification
"""
import os, sys

# Check SUMO_HOME
if "SUMO_HOME" not in os.environ:
    print("[X] SUMO_HOME not set. Please set it to your SUMO installation path.")
    print("Example: set SUMO_HOME=C:\\Program Files\\SUMO")
    sys.exit(1)

print("[OK] SUMO_HOME:", os.environ["SUMO_HOME"])

# Add SUMO tools to path
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

try:
    import traci
    import sumolib
    print("[OK] SUMO Python tools imported successfully")
except ImportError as e:
    print("[X] Failed to import SUMO tools:", e)
    sys.exit(1)

# Check files exist
files = ["simulation.sumocfg", "network.net.xml", "routes.rou.xml"]
for f in files:
    if os.path.exists(f):
        print(f"[OK] {f} found")
    else:
        print(f"[X] {f} missing")

print("\nSetup verification complete. Run: python neuromorphic_controller.py")