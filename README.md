# UrbanFlow AI

**NEURAX HACKATHON 3.0 — Urban Traffic Flow, Incident Intelligence & Network Optimization**

---

## 1. Project Overview

UrbanFlow AI is a software-only AI traffic decision-support system designed for Hyderabad-like urban traffic conditions.

The system uses **SUMO (Simulation of Urban MObility)** as its core simulation environment. AI models analyze simulated traffic data to detect congestion, identify abnormal behavior, forecast future conditions, and recommend interventions. Those interventions are tested back inside SUMO, and the results are compared before being presented on a decision-support dashboard.

> SUMO is the traffic simulation core. AI understands and predicts the traffic. The decision engine proposes actions. SUMO tests those actions. Impact evaluation measures the difference. The dashboard presents the evidence.

---

## 2. Problem Statement

Urban traffic management in dense cities like Hyderabad is challenging because of:

- **Peak-hour demand** — traffic volumes far exceed road capacity during morning and evening peaks
- **Recurring bottlenecks** — the same junctions and corridors congest repeatedly
- **Road-capacity limitations** — fixed infrastructure cannot adapt to demand spikes
- **Signalized junctions** — poorly timed signals create unnecessary delays and spillback
- **Road works** — lane closures reduce capacity and shift traffic unpredictably
- **Incidents** — breakdowns, accidents, and blockages cause sudden disruptions
- **Congestion spillback** — queues on one road propagate backward and affect adjacent roads
- **Rapidly changing conditions** — traffic states shift faster than manual operators can respond

---

## 3. Objectives

| # | Objective |
|---|-----------|
| 1 | Analyze traffic and road-network data |
| 2 | Detect congestion using simulated traffic indicators |
| 3 | Detect abnormal traffic behavior |
| 4 | Identify supported incident scenarios |
| 5 | Forecast traffic conditions at +15, +30, +45, and +60 minutes |
| 6 | Recommend simulated traffic diversions |
| 7 | Identify recurring bottlenecks |
| 8 | Simulate hypothetical infrastructure modifications |
| 9 | Compare baseline and modified SUMO simulations (before/after) |

---

## 4. SUMO-Centered Architecture

```
Traffic / Road Network Data
          ↓
   SUMO Simulation
   (Network + Vehicles + Demand + Signals)
          ↓
  TraCI / Data Collection
  (Speed, Flow, Occupancy, Queue, Travel Time)
          ↓
    Data Processing
          ↓
   AI Traffic Analysis
   (Congestion · Anomaly · Incident · Bottleneck)
          ↓
  Traffic Forecasting
  (+15 / +30 / +45 / +60 min)
          ↓
    Decision Engine
       ↙        ↘
Diversion     Infrastructure
Scenario       Scenario
       ↘        ↙
  Counterfactual SUMO Simulation
          ↓
   Impact Evaluation
   (Before vs After)
          ↓
  Decision-Support Dashboard
```

Both the diversion scenario and the infrastructure scenario are fed back into SUMO for simulation. The results are compared against the baseline before any recommendation is presented.

---

## 5. System Workflow

### Stage 1 — Traffic and Road Network

The road network is defined using SUMO-compatible files (`.net.xml`, `.rou.xml`, `.add.xml`). Traffic demand, vehicle routes, and signal plans are configured to represent peak-hour urban conditions. Controlled incident scenarios (e.g., lane blockage, road works) are prepared as separate SUMO scenario files.

### Stage 2 — SUMO Simulation

SUMO runs the defined network and demand as a time-stepped simulation. It models vehicle movement, signal phases, lane changes, and queue formation. SUMO is the single source of ground-truth traffic state for the entire system.

### Stage 3 — Traffic Data Collection

TraCI (Traffic Control Interface) and SUMO output files provide per-road, per-timestep data:

| Field | Description |
|-------|-------------|
| Road ID | Identifier of the road segment |
| Timestamp | Simulation time step |
| Vehicle Count | Number of vehicles on the segment |
| Average Speed | Mean speed of vehicles (m/s or km/h) |
| Traffic Flow | Vehicles passing a point per unit time |
| Occupancy | Fraction of time a detector is occupied |
| Queue Length | Number of vehicles waiting |
| Travel Time | Time to traverse the segment |

### Stage 4 — AI Traffic Analysis

- **Congestion detection** — classifies road segments as free-flow, slow, or congested based on speed, occupancy, and flow thresholds
- **Abnormal traffic detection** — flags unusual patterns such as sudden speed drops, unexpected queue formation, or flow reversals
- **Incident detection** — identifies supported scenarios (lane blockage, road works, stalled vehicle) from traffic signatures
- **Recurring bottleneck detection** — aggregates historical simulation runs to find segments that congest repeatedly

### Stage 5 — Traffic Forecasting

A forecasting model predicts traffic conditions on key road segments at:

- **+15 minutes** — short-term, high confidence
- **+30 minutes** — medium-term
- **+45 minutes** — medium-term
- **+60 minutes** — longer-term, wider uncertainty

Forecasts are used by the decision engine to act before congestion peaks rather than after.

### Stage 6 — Decision Engine

The decision engine receives the current traffic state, detected incidents, and forecasts, then:

- Analyzes the road network graph for alternative routes (using NetworkX)
- Generates a **diversion scenario** — a candidate re-routing of traffic away from the congested segment
- Selects a **recurring bottleneck** and generates a **hypothetical infrastructure scenario** (e.g., added lane, signal retiming, turn restriction removal)

### Stage 7 — Counterfactual SUMO Simulation

The proposed scenario (diversion or infrastructure modification) is applied to the SUMO network and re-simulated. The baseline simulation (no change) and the proposed simulation run under identical demand conditions so results are directly comparable.

### Stage 8 — Impact Evaluation

The following metrics are compared between baseline and proposed scenarios:

| Metric | Description |
|--------|-------------|
| Travel Time | Average time to complete a trip |
| Average Speed | Mean network speed |
| Queue Length | Average and maximum queue on affected segments |
| Throughput | Total vehicles completing trips |
| Delay | Extra time compared to free-flow travel |
| Congestion Duration | How long a segment remains congested |

### Stage 9 — Dashboard

The decision-support dashboard presents:

- Live and historical simulation state on a map
- Congestion and anomaly alerts
- Traffic forecasts (+15 to +60 min)
- Recommended diversions with supporting evidence
- Before/after impact comparison charts
- Assumptions and limitations for each recommendation

---

## 6. Architecture Diagram

```
                    ┌───────────────────────┐
                    │  Traffic / Road Data  │
                    │  .net.xml  .rou.xml   │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │    SUMO Simulation    │
                    │  Network + Vehicles   │
                    │  Demand + Signals     │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  TraCI / Data Output  │
                    │  Speed · Flow · Queue │
                    │  Occupancy · TravelT  │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │    Data Processing    │
                    │  Cleaning · Features  │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  AI Traffic Analysis  │
                    │  Congestion · Anomaly │
                    │  Incident · Bottleneck│
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Traffic Forecasting  │
                    │  +15/+30/+45/+60 min  │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │    Decision Engine    │
                    │  Routing · Scenarios  │
                    └─────────┬─────────────┘
                              │
               ┌──────────────┴──────────────┐
               │                             │
               ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │    Diversion    │           │ Infrastructure  │
    │    Scenario     │           │    Scenario     │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             └──────────────┬──────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  Counterfactual SUMO  │
                │     Simulation        │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │   Impact Evaluation   │
                │    Before vs After    │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  Decision Dashboard   │
                │  Map · Charts · Alerts│
                └───────────────────────┘
```

---

## 7. Project Structure

```
UrbanFlow-AI/
│
├── README.md
│
├── sumo/
│   ├── network/              # Road network files (.net.xml)
│   ├── routes/               # Vehicle demand and route files (.rou.xml)
│   ├── scenarios/
│   │   ├── baseline/         # Normal peak-hour simulation
│   │   ├── incident/         # Controlled incident scenarios
│   │   ├── diversion/        # Re-routing scenarios
│   │   └── infrastructure/   # Hypothetical network modifications
│   └── simulation.sumocfg    # Main SUMO configuration file
│
├── data/
│   ├── raw/                  # Raw TraCI / SUMO output data
│   ├── processed/            # Cleaned and feature-engineered data
│   └── outputs/              # Simulation result files
│
├── traffic_analysis/
│   ├── congestion.py         # Congestion detection logic
│   ├── anomaly.py            # Abnormal traffic detection
│   └── incident.py           # Incident classification
│
├── forecasting/
│   ├── train.py              # Model training
│   ├── predict.py            # +15/+30/+45/+60 min predictions
│   └── evaluation.py         # Forecast accuracy metrics
│
├── decision_engine/
│   ├── routing.py            # Network graph and route analysis
│   ├── diversion.py          # Diversion scenario generation
│   └── infrastructure.py     # Infrastructure scenario generation
│
├── simulation/
│   ├── traci_controller.py   # TraCI connection and data collection
│   ├── scenario_runner.py    # Runs baseline and proposed scenarios
│   └── impact_evaluation.py  # Before/after metric comparison
│
├── dashboard/
│   ├── app.py                # Main dashboard application
│   ├── maps.py               # Map rendering
│   └── charts.py             # Charts and metric visualizations
│
├── models/                   # Saved trained model files
├── requirements.txt
└── main.py                   # Entry point
```

**Folder summary:**

| Folder | Purpose |
|--------|---------|
| `sumo/` | All SUMO network, route, and scenario configuration files |
| `data/` | Raw outputs from SUMO, processed features, and result files |
| `traffic_analysis/` | AI modules for congestion, anomaly, and incident detection |
| `forecasting/` | Traffic forecasting model — training, prediction, evaluation |
| `decision_engine/` | Routing analysis, diversion and infrastructure scenario logic |
| `simulation/` | TraCI controller, scenario runner, and impact evaluation |
| `dashboard/` | Decision-support dashboard — maps, charts, and alerts |
| `models/` | Persisted trained model artifacts |

---

## 8. Technology Stack

| Technology | Role |
|------------|------|
| **SUMO** | Core traffic simulation environment |
| **TraCI** | Python API to interact with SUMO at runtime |
| **Python** | Primary programming language |
| **Pandas / NumPy** | Data processing and feature engineering |
| **Scikit-learn** | Congestion detection, anomaly detection, forecasting models |
| **NetworkX** | Road network graph analysis and route finding |
| **FastAPI** | Backend API layer (optional, if dashboard is decoupled) |
| **Streamlit / React** | Decision-support dashboard frontend |
| **Plotly** | Interactive charts and metric visualizations |
| **SQLite / PostgreSQL** | Storing simulation results and historical data (if required) |

Not every technology listed above is mandatory. The core stack is SUMO + TraCI + Python + a dashboard framework.

---

## 9. Team Responsibilities

| Role | Responsibility |
|------|---------------|
| AI / ML | Congestion detection, anomaly detection, forecasting models, impact evaluation metrics |
| SUMO / Simulation | Road network setup, demand and route files, TraCI integration, scenario configuration |
| Backend / Decision Engine | Routing logic, diversion and infrastructure scenario generation, scenario execution |
| Frontend / Integration | Dashboard, map rendering, charts, system integration and end-to-end wiring |

---

## 10. Demo Scenario

The demonstration follows this sequence:

1. Start a SUMO peak-hour simulation of the urban network
2. Display the road network and live vehicle positions on the dashboard
3. Detect a congested road segment using AI analysis
4. Show the traffic indicators (speed, occupancy, queue length) that triggered the classification
5. Introduce or detect a controlled abnormal scenario (e.g., lane blockage)
6. Display +15, +30, +45, and +60 minute traffic forecasts for affected segments
7. Generate a candidate diversion route using the decision engine
8. Run the diversion scenario inside SUMO
9. Compare baseline and diversion results (travel time, queue, throughput)
10. Identify a recurring bottleneck from aggregated simulation history
11. Apply a hypothetical infrastructure modification (e.g., added lane or signal retiming)
12. Run the modified SUMO scenario
13. Show before/after impact on the dashboard
14. Display the reasoning, evidence, assumptions, and limitations for each recommendation

---

## 11. Evaluation Metrics

| Metric | Description |
|--------|-------------|
| Average Travel Time | Mean time for vehicles to complete their trips |
| Average Speed | Mean speed across the network or affected corridor |
| Queue Length | Average and peak queue on congested segments |
| Throughput | Total number of vehicles completing trips in the simulation period |
| Delay | Extra travel time compared to free-flow conditions |
| Congestion Duration | How long a segment remains above the congestion threshold |
| Forecast Error | MAE / RMSE between predicted and simulated traffic values |

---

## 12. Scope and Limitations

UrbanFlow AI is a **software-only, simulation-based, advisory system**.

All traffic actions, diversions, and infrastructure modifications are simulated inside SUMO. No real-world infrastructure is accessed or controlled.

The project does **not** include:

- Live traffic signal control
- CCTV or camera feed access
- GPS-device integration
- Roadside sensor integration
- Municipal infrastructure control
- Actual road construction or physical changes

All results are based on SUMO simulations and are intended to support decision-making, not to replace it.

---

## 13. Future Scope

- Integration with real-time traffic data feeds
- Weather and event data as simulation inputs
- Roadside sensor and traffic camera analytics
- Advanced spatiotemporal forecasting models (e.g., GNN, Transformer)
- Scaling to larger city-wide road networks
- Digital-twin traffic simulation with continuous data synchronization

---

## 14. Getting Started

**Prerequisites:** SUMO and Python 3.9+ must be installed.

- SUMO: https://sumo.dlr.de/docs/Installing/index.html
- Python: https://www.python.org/downloads/

```bash
# 1. Clone or open the project
cd UrbanFlow-AI

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Set the SUMO_HOME environment variable
# Windows:
set SUMO_HOME=C:\path\to\sumo
# macOS / Linux:
export SUMO_HOME=/path/to/sumo

# 6. Run the baseline simulation
python simulation/scenario_runner.py --scenario baseline

# 7. Start the application
python main.py
```

> Replace `C:\path\to\sumo` or `/path/to/sumo` with your actual SUMO installation directory.

---

## 15. Project Status

```
Project   : UrbanFlow AI
Hackathon : NEURAX HACKATHON 3.0
Type      : Software-only AI traffic decision-support system
Simulation: SUMO (Simulation of Urban MObility)
Status    : In Development
Team      : [Your Team Name]
```

---

*UrbanFlow AI — NEURAX HACKATHON 3.0*
