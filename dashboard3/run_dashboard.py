#!/usr/bin/env python3
"""
Simple script to run the SUMO Live Dashboard
"""

import os
import sys
import subprocess

def check_sumo_home():
    """Check if SUMO_HOME is set"""
    if "SUMO_HOME" not in os.environ:
        print("❌ SUMO_HOME environment variable not set!")
        print("Please set SUMO_HOME to your SUMO installation directory")
        print("Example: set SUMO_HOME=C:\\Program Files (x86)\\Eclipse\\Sumo")
        return False
    
    sumo_home = os.environ["SUMO_HOME"]
    print(f"✅ SUMO_HOME: {sumo_home}")
    
    # Check if sumo-gui exists
    sumo_gui = os.path.join(sumo_home, "bin", "sumo-gui.exe")
    if not os.path.exists(sumo_gui):
        sumo_gui = os.path.join(sumo_home, "bin", "sumo-gui")
        if not os.path.exists(sumo_gui):
            print(f"❌ sumo-gui not found in {sumo_home}/bin/")
            return False
    
    print(f"✅ Found sumo-gui: {sumo_gui}")
    return True

def check_files():
    """Check if required files exist"""
    required_files = [
        "simulation.sumocfg",
        "network.net.xml",
        "routes.rou.xml",
        "templates/dash_board.html",
        "static/dash_board.css",
        "static/dash_board.js"
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        return False
    
    print("✅ All required files found")
    return True

def install_requirements():
    """Install required Python packages"""
    try:
        import flask
        import flask_cors
        import cv2
        import numpy
        print("✅ All Python packages available")
        return True
    except ImportError as e:
        print(f"❌ Missing Python package: {e}")
        print("Installing required packages...")
        
        packages = ["flask", "flask-cors", "opencv-python", "numpy"]
        for package in packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"✅ Installed {package}")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {package}")
                return False
        
        return True

def main():
    """Main function"""
    print("🚦 SUMO Live Dashboard Startup")
    print("=" * 40)
    
    # Check SUMO installation
    if not check_sumo_home():
        input("Press Enter to exit...")
        return
    
    # Check required files
    if not check_files():
        input("Press Enter to exit...")
        return
    
    # Install requirements
    if not install_requirements():
        input("Press Enter to exit...")
        return
    
    print("\n🚀 Starting SUMO Live Dashboard...")
    print("📺 Dashboard will be available at: http://localhost:5000")
    print("🎮 Use the web interface to control the simulation")
    print("⏹️  Press Ctrl+C to stop the dashboard")
    print("=" * 40)
    
    try:
        # Import and run the dashboard
        from live_sumo_dashboard import app, dashboard
        app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
    except KeyboardInterrupt:
        print("\n🛑 Dashboard stopped by user")
    except Exception as e:
        print(f"\n❌ Error running dashboard: {e}")
    finally:
        # Cleanup
        try:
            dashboard.stop_sumo()
        except:
            pass
        
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()