import os
import sys
import time
import cv2
import traci
import subprocess
from flask import Flask, Response, request, render_template, jsonify
from flask_cors import CORS

# ------------------------
# SUMO Environment
# ------------------------
if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    sys.path.append(tools)
else:
    raise EnvironmentError("Please set SUMO_HOME environment variable")

# sumoBinary = "sumo-gui"  # or "sumo" for headless
# # <<< CHANGE THIS to your actual config path >>>
# sumoConfig = r"C:\Users\dhars\OneDrive\Desktop\dashboard2\sumo\simulation.sumocfg"
# sumoPort = 8813

# # Start SUMO-GUI with smaller step-length for smoother motion
# sumoProcess = subprocess.Popen([
#     sumoBinary,
#     "-c", sumoConfig,
#     "--start",
#     "--step-length", "0.1",        # finer steps
#     "--remote-port", str(sumoPort)
# ])
# time.sleep(0.5)

# # Connect to TraCI
# connected = False
# for i in range(10):
#     try:
#         traci.init(sumoPort)
#         connected = True
#         print(f"Connected to SUMO on port {sumoPort}")
#         break
#     except Exception:
#         print("Waiting for SUMO to start...")
#         time.sleep(1)

# if not connected:
#     sumoProcess.terminate()
#     sumoProcess.wait()
#     raise ConnectionError(f"Could not connect to SUMO on port {sumoPort}")

# ------------------------
# Flask App
# ------------------------
app = Flask(__name__)
CORS(app)

# ------------------------
# Live Feed Generator
# ------------------------
# view_id = None

# def generate_frames():
#     """Yield JPEG frames from SUMO GUI screenshots."""
#     global view_id
#     if view_id is None:
#         view_id = traci.gui.getIDList()[0]
#         print("Using SUMO view:", view_id)

#     while True:
#         try:
#             # advance simulation multiple steps per frame for faster vehicle motion
#             for _ in range(5):
#                 traci.simulationStep()

#             # take screenshot
#             screenshot_path = "frame.png"
#             traci.gui.screenshot(view_id, screenshot_path)
#             frame = cv2.imread(screenshot_path)
#             if frame is None:
#                 continue

#             # JPEG encode at lower quality to reduce lag
#             ret, buffer = cv2.imencode(".jpg", frame,
#                                        [int(cv2.IMWRITE_JPEG_QUALITY), 60])
#             if not ret:
#                 continue

#             yield (b'--frame\r\n'
#                    b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

#             # throttle FPS a bit
#             time.sleep(0.05)
#         except Exception as e:
#             print("Error streaming frame:", e)
#             continue

# ------------------------
# Routes
# ------------------------
@app.route("/")
def index():
    return render_template("dash_board.html")

from flask import redirect

@app.route("/live")
def live_feed():
    # RL script is streaming on port 5000
    return redirect("http://127.0.0.1:5000/live")
   

@app.route("/signal", methods=["POST"])
def set_signal():
    data = request.json
    command = data.get("command")
    tls_id = "0"  # your intersection ID in SUMO

    try:
        if command == "all_red":
            traci.trafficlight.setRedYellowGreenState(tls_id, "rrrr")
        elif command == "ns_green":
            traci.trafficlight.setRedYellowGreenState(tls_id, "GGrr")
        elif command == "ew_green":
            traci.trafficlight.setRedYellowGreenState(tls_id, "rrGG")
        elif command == "all_yellow":
            traci.trafficlight.setRedYellowGreenState(tls_id, "yyyy")
        elif command == "flash_red":
            traci.trafficlight.setRedYellowGreenState(tls_id, "rrrr")
        elif command == "flash_yellow":
            traci.trafficlight.setRedYellowGreenState(tls_id, "yyyy")
        elif command == "emergency":
            traci.trafficlight.setRedYellowGreenState(tls_id, "GGGG")
        elif command == "auto_cycle":
            traci.trafficlight.setProgram(tls_id, "0")
        elif command == "manual":
            pass
        else:
            return jsonify({"status": "error",
                            "message": "Unknown command"}), 400

        state = traci.trafficlight.getRedYellowGreenState(tls_id)
        return jsonify({"status": "ok",
                        "command": command,
                        "state": state})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------------
# Run Flask + shutdown SUMO properly
# ------------------------
if __name__ == "__main__":
    print("Dashboard Flask running at http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
