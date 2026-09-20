# AI Urban Traffic Congestion Forecasting & Network Intelligence System

An AI-Powered decision-support platform for urban traffic management, congestion forecasting (+15m, +30m, +45m, +60m), spatial propagation analysis, bottleneck detection, intervention recommendation, and counterfactual scenario simulation.

---

## System Architecture

```
traffic-intelligence/
├── backend/
│   ├── api/             # FastAPI endpoints
│   ├── core/            # NetworkX graph representation & routing
│   ├── intelligence/    # Propagation, Incidents, Roadworks, Bottlenecks, Interventions, Counterfactuals
│   └── schemas/         # Pydantic data models
├── ml/
│   ├── preprocessing/   # Noise handling, stuck sensor & spike cleaning
│   ├── features/        # Feature engineering (temporal, lags, rolling, network, incident, OD)
│   ├── models/          # Trained models
│   ├── train.py         # Multi-horizon model trainer (LightGBM, HistGradientBoosting, ExtraTrees)
│   ├── evaluate.py      # Time-aware out-of-sample validator
│   └── predict.py       # Inference service & XAI explanation generator
├── frontend/
│   ├── index.html       # Leaflet OSM Dashboard
│   ├── app.js           # Interactive UI logic & chart rendering
│   └── style.css
├── simulation/
│   └── sumo/            # SUMO simulation interface & mock simulator
├── reports/             # Dataset profiles, evaluation results, feature lineage
├── tests/               # Automated unit test suite
├── pipeline.py          # End-to-end single-command runner
└── main.py              # FastAPI server entry point
```

---

## Key Features

1. **Multi-Horizon Traffic Forecasting:** Predicts Speed, Flow, and Congestion Index across +15m, +30m, +45m, +60m horizons.
2. **Network Topology Graph:** Directed NetworkX representation supporting upstream/downstream search, bottleneck detection, and spatial traversal.
3. **Congestion Propagation Analysis:** Tracks queue spillback (upstream), flow pressure (downstream), and lateral intersection spillover.
4. **Bottleneck Detection:** Identifies recurring and dynamic bottlenecks using decomposed factors (frequency, utilization, queue pressure, network importance).
5. **Intervention Recommendation Engine:** Scores and ranks planning candidate interventions by demand pressure, feasibility, and cost index.
6. **Counterfactual Simulation Engine:** Simulates "what-if" capacity upgrade scenarios against baseline predictions.
7. **Explainable AI (XAI):** Provides per-prediction feature contribution rankings.
8. **Professional Decision-Support Dashboard:** Interactive Leaflet OSM map with custom color coding (Green/Yellow/Orange/Red), horizon toggles, and Chart.js forecast timeline visualizers.

---

## Quick Start

### 1. Run Full End-to-End Pipeline
```bash
python pipeline.py
```

### 2. Run Automated Test Suite
```bash
python tests/test_all.py
```

### 3. Launch Decision-Support Dashboard & API
```bash
python main.py
```
Then open `http://localhost:8000` in your web browser.

---

## API Endpoints Overview

- `GET /health`: System health & loaded model count
- `GET /network`: GeoJSON road network
- `GET /traffic/current`: Current traffic observation state
- `GET /traffic/forecast?horizon=15m`: Multi-horizon predicted traffic state
- `GET /traffic/segment/{segment_id}`: Full segment details, forecast, XAI, & recommended interventions
- `GET /incidents`: Active incidents & impact analysis
- `GET /bottlenecks`: Top bottleneck segments
- `GET /propagation/{segment_id}`: Spatial congestion propagation traversal
- `GET /interventions`: AI-ranked candidate interventions
- `POST /counterfactual`: Run counterfactual "what-if" intervention scenario
