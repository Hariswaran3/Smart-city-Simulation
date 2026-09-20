#!/usr/bin/env python3
"""
Flask Backend for Smart Traffic Management Dashboard
Displays SUMO live feed + RL-controlled signal states (4 intersections)
"""

import os
import json
import time
import threading
import cv2
import numpy as np
from flask import Flask, render_template, jsonify, Response
from flask_cors import CORS

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Files written by RL controller
SCREENSHOT_FILE = os.path.join(os.path.dirname(__file__), "latest_screenshot.jpg")
SIGNAL_STATE_FILE = os.path.join(os.path.dirname(__file__), "signal_states.json")

# Global memory
latest_frame = None
signal_states = {
    "A": {"phase": "red"},
    "B": {"phase": "red"},
    "C": {"phase": "red"},
    "D": {"phase": "red"}
}


def file_watcher():
    """Background thread: watch screenshot file and JSON state file"""
    global latest_frame, signal_states
    last_img_mtime = 0
    last_json_mtime = 0

    while True:
        try:
            # Watch screenshot file
            if os.path.exists(SCREENSHOT_FILE):
                mtime = os.path.getmtime(SCREENSHOT_FILE)
                if mtime != last_img_mtime:
                    # slight delay to avoid partial write
                    time.sleep(0.02)
                    with open(SCREENSHOT_FILE, "rb") as f:
                        latest_frame = f.read()
                    last_img_mtime = mtime

            # Watch signal JSON file
            if os.path.exists(SIGNAL_STATE_FILE):
                mtime = os.path.getmtime(SIGNAL_STATE_FILE)
                if mtime != last_json_mtime:
                    with open(SIGNAL_STATE_FILE, "r") as f:
                        data = json.load(f)
                        signal_states = data
                    last_json_mtime = mtime

            time.sleep(0.1)
        except Exception as e:
            print(f"[Watcher error] {e}")
            time.sleep(1)


@app.route("/")
def index():
    """Serve dashboard HTML"""
    return render_template("dash_board.html")


@app.route("/live")
def live_feed():
    """Stream the live SUMO feed (screenshot sequence)"""
    def generate():
        boundary = b"--frame\r\n"
        while True:
            try:
                if latest_frame:
                    yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + latest_frame + b"\r\n"
                else:
                    # placeholder if no feed
                    img = np.zeros((400, 600, 3), dtype=np.uint8)
                    cv2.putText(img, "No Feed Available", (80, 200),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    _, buffer = cv2.imencode(".jpg", img)
                    yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"

                time.sleep(0.1)
            except GeneratorExit:
                break
            except Exception as e:
                print(f"Live feed error: {e}")
                time.sleep(0.5)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    """Return the current mode and 4 intersection signal states"""
    return jsonify({
        "simulation_running": True,
        "intersections": signal_states
    })


@app.route("/api/control", methods=["POST"])
def api_control():
    """Dummy control endpoint for RL viewer"""
    try:
        from flask import request
        data = request.get_json()
        action = data.get("action", "")
        # Since this backend is a read-only viewer for the RL controller,
        # we don't actually control SUMO from here. We just return success.
        return jsonify({
            "success": True, 
            "message": f"Action '{action}' ignored. RL Controller is managing simulation."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    # Start file watcher thread
    threading.Thread(target=file_watcher, daemon=True).start()

    print("🚦 Backend started at http://localhost:5000")
    print("📺 Live feed at /live, API at /api/status")

    # Ensure template/static dirs exist
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    app.run(debug=True, host="0.0.0.0", port=5002, threaded=True)
