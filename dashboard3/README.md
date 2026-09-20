# SUMO Live Dashboard

A real-time dashboard for SUMO traffic simulation with live video streaming and traffic light status monitoring.

## Features

🎥 **Live SUMO Simulation Stream**
- Real-time video feed from SUMO-GUI
- No recorded videos - live simulation streaming
- Smooth 10 FPS streaming with optimized performance

🚦 **Traffic Light Status Display**
- Real-time traffic light states for each intersection
- Lane-specific information (vehicle count, waiting time)
- Visual indicators for congested lanes
- Support for up to 4 intersections (A, B, C, D)

🎮 **Simulation Control**
- Start/Stop/Reset simulation from web interface
- Manual traffic light control
- Emergency mode support
- Fullscreen simulation view

📊 **Live Metrics**
- Total vehicles in simulation
- Average waiting times
- Congestion levels
- Throughput monitoring

## Quick Start

### Method 1: Windows Batch File (Easiest)
1. Double-click `run_dashboard.bat`
2. Open browser to http://localhost:5000
3. Click "Start" to begin simulation

### Method 2: Python Script
```bash
python run_dashboard.py
```

### Method 3: Direct Execution
```bash
python live_sumo_dashboard.py
```

## Requirements

### Software
- Python 3.7+
- SUMO (Eclipse SUMO traffic simulator)
- Web browser (Chrome, Firefox, Edge)

### Python Packages
- Flask
- Flask-CORS
- OpenCV (cv2)
- NumPy

*Note: The startup script will automatically install missing packages*

### SUMO Setup
1. Install SUMO from https://eclipse.org/sumo/
2. Set SUMO_HOME environment variable:
   ```
   Windows: set SUMO_HOME=C:\Program Files (x86)\Eclipse\Sumo
   Linux: export SUMO_HOME=/usr/share/sumo
   ```

## File Structure

```
dashboard3/
├── live_sumo_dashboard.py    # Main dashboard server
├── run_dashboard.py          # Startup script with checks
├── run_dashboard.bat         # Windows batch file
├── simulation.sumocfg        # SUMO configuration
├── network.net.xml           # Road network
├── routes.rou.xml           # Vehicle routes
├── templates/
│   └── dash_board.html      # Web interface
├── static/
│   ├── dash_board.css       # Styling
│   └── dash_board.js        # Frontend logic
└── saved_models/            # RL models (optional)
```

## Usage

1. **Start Dashboard**: Run the startup script
2. **Open Browser**: Navigate to http://localhost:5000
3. **Start Simulation**: Click the "Start" button
4. **Monitor Traffic**: Watch live simulation and traffic light status
5. **Control Signals**: Use manual control buttons if needed

## Dashboard Interface

### Left Panel
- **SUMO Simulator**: Live video stream from simulation
- **Controls**: Start, Stop, Reset, Fullscreen buttons
- **Traffic Light Status**: Real-time signal states with lane info

### Right Panel
- **Manual Signal Control**: Override automatic control
- **Status Information**: Current mode, phase, flow status
- **Live Metrics**: Vehicle counts, waiting times, congestion

## Traffic Light Display

Each intersection shows:
- 🔴 Red/🟡 Yellow/🟢 Green light status
- **N/S/E/W Lane Info**: Vehicle count and waiting time
- **Congestion Indicators**: Red background for congested lanes (>30s wait)

## Troubleshooting

### Common Issues

**"SUMO_HOME not set"**
- Set the SUMO_HOME environment variable to your SUMO installation

**"No traffic lights found"**
- Ensure your SUMO network has traffic lights defined
- Check simulation.sumocfg and network.net.xml files

**"Connection failed"**
- Make sure no other SUMO instance is running
- Check if port 8813 is available

**"No video feed"**
- Ensure SUMO-GUI (not headless SUMO) is running
- Check if screenshot files are being created

### Performance Tips

- Close unnecessary applications for better streaming
- Use lower resolution for better performance
- Reduce simulation step-length for smoother animation

## Advanced Features

### RL Integration
The dashboard can work with reinforcement learning controllers:
- Load trained models from `saved_models/`
- Real-time learning and adaptation
- Emergency vehicle priority
- Right-turn optimization

### API Endpoints

- `GET /`: Dashboard interface
- `GET /live`: Live video stream
- `GET /api/status`: Current simulation status
- `POST /api/control`: Send control commands

## Development

To modify the dashboard:

1. **Backend**: Edit `live_sumo_dashboard.py`
2. **Frontend**: Edit files in `templates/` and `static/`
3. **Styling**: Modify `static/dash_board.css`
4. **Behavior**: Update `static/dash_board.js`

## License

This project is part of the Smart India Hackathon (SIH) submission for intelligent traffic management systems.