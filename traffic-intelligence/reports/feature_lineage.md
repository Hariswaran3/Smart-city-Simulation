# Feature Lineage and Leakage Prevention Rules

## Overview
Every feature used in the AI Traffic Intelligence System is strictly audited for availability at prediction time ($t$).
No forecast target columns or future information are EVER included as features.

---

## Complete Feature Lineage

| Feature Name | Source Table | Available At | Horizon Scope | Leakage Prevention Strategy |
|--------------|--------------|--------------|---------------|-----------------------------|
| `speed_kmh` | `traffic_train.csv` | $t$ | All ($15m, 30m, 45m, 60m$) | Observed current speed |
| `flow_vph` | `traffic_train.csv` | $t$ | All | Observed current traffic flow |
| `occupancy_pct` | `traffic_train.csv` | $t$ | All | Observed current detector occupancy |
| `congestion_index` | `traffic_train.csv` | $t$ | All | Calculated observed congestion index |
| `delay_min` | `traffic_train.csv` | $t$ | All | Observed current segment delay |
| `queue_length_veh` | `traffic_train.csv` | $t$ | All | Observed current queue length |
| `travel_time_min` | `traffic_train.csv` | $t$ | All | Observed travel time |
| `free_flow_time_min` | `traffic_train.csv` | $t$ | All | Static segment attribute |
| `sensor_quality` | `traffic_train.csv` | $t$ | All | Detector quality metric |
| `hour`, `minute`, `day_of_week` | `timestamp` | $t$ | All | Temporal calendar features |
| `hour_sin`, `hour_cos`, `dow_sin`, `dow_cos` | derived from `timestamp` | $t$ | All | Cyclical time encodings |
| `is_weekend`, `is_peak`, `is_am_peak`, `is_pm_peak` | derived | $t$ | All | Standard peak hour indicators |
| `speed_kmh_lag_1` (5 min lag) | `traffic_train` ($t-1$) | $t$ | All | Calculated using strict segment-level shift |
| `speed_kmh_lag_2` (10 min lag) | `traffic_train` ($t-2$) | $t$ | All | Calculated using strict segment-level shift |
| `speed_kmh_lag_3` (15 min lag) | `traffic_train` ($t-3$) | $t$ | All | Calculated using strict segment-level shift |
| `speed_kmh_lag_6` (30 min lag) | `traffic_train` ($t-6$) | $t$ | All | Calculated using strict segment-level shift |
| `speed_kmh_lag_12` (60 min lag) | `traffic_train` ($t-12$) | $t$ | All | Calculated using strict segment-level shift |
| `*_roll_mean_15min`, `30min`, `60min` | `traffic_train` ($t-W:t$) | $t$ | All | Backward-looking rolling windows only |
| `*_roll_std_15min`, `min`, `max` | `traffic_train` ($t-W:t$) | $t$ | All | Backward-looking rolling windows only |
| `lanes`, `capacity_vph`, `length_km`, `grade_pct` | `network.csv` | Static | All | Static road topology |
| `structural_bottleneck`, `importance` | `network.csv` | Static | All | Structural graph indicators |
| `road_class_encoded`, `has_signal` | `network.csv` | Static | All | Categorical road hierarchy |
| `capacity_utilization`, `delay_ratio`, `speed_ratio` | derived | $t$ | All | Instantaneous ratio features |
| `active_incident`, `incident_severity`, `lanes_blocked` | `incidents_train.csv` | $t$ | All | Filtered for incidents active at timestamp $t$ |
| `active_roadwork`, `roadwork_closure_fraction` | `roadworks_train.csv` | $t$ | All | Filtered for roadworks active at timestamp $t$ |
| `temperature_c`, `rain_intensity`, `event_level`, `holiday_flag` | `context_train.csv` | $t$ | All | System-wide weather & event context at $t$ |
| `od_demand_pressure` | `od_demand_profiles.csv` | Static | All | Endpoint node demand aggregation |
| **`target_speed_15m` ... `target_congestion_60m`** | `forecast_targets_train.csv` | $t+\Delta t$ | **EXCLUDED** | **STRICTLY EXCLUDED** — Labels only |

---

## Leakage Prevention Audit Rules
1. **Target Separation:** The 12 columns in `forecast_targets_*.csv` are strictly stripped from all feature matrices.
2. **Temporal Order:** All tables are sorted by `(segment_id, timestamp)` prior to computing lag or rolling operations.
3. **Rolling Window Boundaries:** Rolling windows are strictly closed on the right and open on the left ($t-W$ to $t$).
4. **Validation Isolation:** Validation dataset features are processed using historical lags within the validation time span ($T_{val}$) only.
