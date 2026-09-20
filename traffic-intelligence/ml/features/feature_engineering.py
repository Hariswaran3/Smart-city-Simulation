"""
Feature Engineering Pipeline
=============================
Generates all input features for multi-horizon traffic forecasting.
Strict leakage prevention: forecast target columns are NEVER included.

Feature groups:
  1. Traffic state (from current observation)
  2. Temporal (hour, minute, day-of-week, cyclical encodings)
  3. Historical lags (1, 2, 3, 6, 12 steps = 5, 10, 15, 30, 60 min)
  4. Rolling statistics (15, 30, 60 min windows)
  5. Road/network static features
  6. Incident features (active at time t)
  7. Roadwork features (active at time t)
  8. Context / weather / event features
  9. Derived network-topology features (capacity utilization, delay ratio)
"""

import logging
import numpy as np
import pandas as pd
from typing import List, Optional

logger = logging.getLogger(__name__)

# Sampling interval in minutes
SAMPLE_MIN = 5

# Lag steps (in number of 5-min intervals)
LAG_STEPS = {
    "lag_1": 1,    # 5 min
    "lag_2": 2,    # 10 min
    "lag_3": 3,    # 15 min
    "lag_6": 6,    # 30 min
    "lag_12": 12,  # 60 min
}

# Rolling window sizes in steps
ROLLING_WINDOWS = {
    "15min": 3,
    "30min": 6,
    "60min": 12,
}

# Core traffic columns to create lags/rolling for
CORE_TRAFFIC_COLS = [
    "speed_kmh", "flow_vph", "occupancy_pct",
    "congestion_index", "delay_min", "queue_length_veh"
]

# Road class encoding
ROAD_CLASS_MAP = {"collector": 0, "arterial": 1}


def build_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add time-based features from the timestamp column."""
    ts = df["timestamp"]
    df["hour"] = ts.dt.hour
    df["minute"] = ts.dt.minute
    df["day_of_week"] = ts.dt.dayofweek  # 0=Monday
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Cyclical encoding for hour and day_of_week
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    # Peak hours: 7–9 AM and 5–7 PM
    df["is_am_peak"] = ((df["hour"] >= 7) & (df["hour"] < 9)).astype(int)
    df["is_pm_peak"] = ((df["hour"] >= 17) & (df["hour"] < 20)).astype(int)
    df["is_peak"] = ((df["is_am_peak"] == 1) | (df["is_pm_peak"] == 1)).astype(int)
    df["is_night"] = ((df["hour"] < 6) | (df["hour"] >= 22)).astype(int)

    return df


def build_lag_features(df: pd.DataFrame,
                        cols: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Add lag features per segment.
    Data must be sorted by (segment_id, timestamp) before calling.
    """
    if cols is None:
        cols = CORE_TRAFFIC_COLS
    cols = [c for c in cols if c in df.columns]

    for lag_name, steps in LAG_STEPS.items():
        for col in cols:
            new_col = f"{col}_{lag_name}"
            df[new_col] = df.groupby("segment_id")[col].shift(steps)
            logger.debug("Created lag feature: %s", new_col)

    return df


def build_rolling_features(df: pd.DataFrame,
                             cols: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Add rolling statistics per segment.
    Data must be sorted by (segment_id, timestamp) before calling.
    """
    if cols is None:
        cols = ["speed_kmh", "flow_vph", "congestion_index", "delay_min"]
    cols = [c for c in cols if c in df.columns]

    for win_name, win_steps in ROLLING_WINDOWS.items():
        for col in cols:
            grp = df.groupby("segment_id")[col]
            df[f"{col}_roll_mean_{win_name}"] = grp.transform(
                lambda x: x.rolling(win_steps, min_periods=1).mean()
            )
            df[f"{col}_roll_std_{win_name}"] = grp.transform(
                lambda x: x.rolling(win_steps, min_periods=1).std().fillna(0)
            )
            df[f"{col}_roll_min_{win_name}"] = grp.transform(
                lambda x: x.rolling(win_steps, min_periods=1).min()
            )
            df[f"{col}_roll_max_{win_name}"] = grp.transform(
                lambda x: x.rolling(win_steps, min_periods=1).max()
            )

    # Congestion trend (current minus 15-min rolling mean)
    if "congestion_index" in df.columns and "congestion_index_roll_mean_15min" in df.columns:
        df["congestion_trend_15min"] = (
            df["congestion_index"] - df["congestion_index_roll_mean_15min"]
        )
    if "speed_kmh" in df.columns and "speed_kmh_roll_mean_15min" in df.columns:
        df["speed_trend_15min"] = (
            df["speed_kmh"] - df["speed_kmh_roll_mean_15min"]
        )

    return df


def build_network_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived network/road features from static attributes.
    Assumes network columns are already merged into df.
    """
    # Capacity utilization (flow / capacity)
    if "flow_vph" in df.columns and "capacity_vph" in df.columns:
        cap = df["capacity_vph"].replace(0, np.nan)
        df["capacity_utilization"] = (df["flow_vph"] / cap).clip(0, 2.0)

    # Delay ratio (delay / free_flow_time)
    if "delay_min" in df.columns and "free_flow_time_min" in df.columns:
        fft = df["free_flow_time_min"].replace(0, np.nan)
        df["delay_ratio"] = (df["delay_min"] / fft).clip(0, 10.0)

    # Speed ratio (current speed / free-flow speed)
    if "speed_kmh" in df.columns and "free_flow_speed_kmh" in df.columns:
        ffs = df["free_flow_speed_kmh"].replace(0, np.nan)
        df["speed_ratio"] = (df["speed_kmh"] / ffs).clip(0, 1.5)

    # Road class encoding
    if "road_class" in df.columns:
        df["road_class_encoded"] = df["road_class"].map(ROAD_CLASS_MAP).fillna(0).astype(int)

    # Has signal
    if "signal_id" in df.columns:
        df["has_signal"] = df["signal_id"].notna().astype(int)

    return df


def build_incident_features(df: pd.DataFrame,
                              incident_flags: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Merge pre-computed incident flags into the feature DataFrame."""
    if incident_flags is None:
        df["active_incident"] = 0
        df["incident_severity"] = 0
        df["incident_lanes_blocked"] = 0
        df["incident_type_encoded"] = 0
        return df

    inc_cols = ["timestamp", "segment_id", "active_incident",
                "incident_severity", "incident_lanes_blocked", "incident_type_encoded"]
    inc_sub = incident_flags[[c for c in inc_cols if c in incident_flags.columns]]
    df = df.merge(inc_sub, on=["timestamp", "segment_id"], how="left")
    df["active_incident"] = df["active_incident"].fillna(0).astype(int)
    df["incident_severity"] = df["incident_severity"].fillna(0)
    df["incident_lanes_blocked"] = df["incident_lanes_blocked"].fillna(0)
    df["incident_type_encoded"] = df["incident_type_encoded"].fillna(0)
    return df


def build_roadwork_features(df: pd.DataFrame,
                              roadwork_flags: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Merge pre-computed roadwork flags into the feature DataFrame."""
    if roadwork_flags is None:
        df["active_roadwork"] = 0
        df["roadwork_closure_fraction"] = 0.0
        df["roadwork_type_encoded"] = 0
        return df

    rw_cols = ["timestamp", "segment_id", "active_roadwork",
               "roadwork_closure_fraction", "roadwork_type_encoded"]
    rw_sub = roadwork_flags[[c for c in rw_cols if c in roadwork_flags.columns]]
    df = df.merge(rw_sub, on=["timestamp", "segment_id"], how="left")
    df["active_roadwork"] = df["active_roadwork"].fillna(0).astype(int)
    df["roadwork_closure_fraction"] = df["roadwork_closure_fraction"].fillna(0.0)
    df["roadwork_type_encoded"] = df["roadwork_type_encoded"].fillna(0)
    return df


def build_od_demand_features(df: pd.DataFrame,
                               od_demand: Optional[pd.DataFrame] = None,
                               network: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Add OD demand pressure features per segment.
    A segment's demand pressure = sum of base_demand from OD pairs whose
    origin or destination node is an endpoint of that segment.
    """
    if od_demand is None or network is None:
        df["od_demand_pressure"] = 0.0
        return df

    # Build segment→node lookup
    if "source_node" in df.columns and "target_node" in df.columns:
        node_demand = od_demand.groupby("origin_node")["base_demand_vph"].sum().rename("origin_demand")
        dest_demand = od_demand.groupby("destination_node")["base_demand_vph"].sum().rename("dest_demand")

        seg_nodes = df[["segment_id", "source_node", "target_node"]].drop_duplicates()
        seg_nodes = seg_nodes.merge(node_demand, left_on="source_node",
                                    right_index=True, how="left")
        seg_nodes = seg_nodes.merge(dest_demand, left_on="target_node",
                                    right_index=True, how="left")
        seg_nodes["od_demand_pressure"] = (
            seg_nodes["origin_demand"].fillna(0) +
            seg_nodes["dest_demand"].fillna(0)
        )
        df = df.merge(
            seg_nodes[["segment_id", "od_demand_pressure"]].drop_duplicates("segment_id"),
            on="segment_id", how="left"
        )
        df["od_demand_pressure"] = df["od_demand_pressure"].fillna(0)
    else:
        df["od_demand_pressure"] = 0.0

    return df


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """
    Return all valid feature columns (exclude ID columns, targets, raw timestamps).
    This is the canonical feature set used for model training.
    """
    exclude_prefixes = ("target_",)
    exclude_exact = {
        "timestamp", "segment_id", "source_node", "target_node",
        "road_class", "signal_id"
    }
    cols = []
    for c in df.columns:
        if c in exclude_exact:
            continue
        if any(c.startswith(p) for p in exclude_prefixes):
            continue
        if df[c].dtype in [object]:
            continue
        cols.append(c)
    return cols


def run_full_feature_pipeline(
    traffic_df: pd.DataFrame,
    incident_flags: Optional[pd.DataFrame] = None,
    roadwork_flags: Optional[pd.DataFrame] = None,
    od_demand: Optional[pd.DataFrame] = None,
    network: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Apply all feature engineering steps to the traffic DataFrame.

    Args:
        traffic_df: merged traffic + network + context DataFrame
        incident_flags: output of get_incident_active_flags()
        roadwork_flags: output of get_roadwork_active_flags()
        od_demand: od_demand_profiles DataFrame
        network: network DataFrame (for demand feature join)

    Returns:
        Feature-enriched DataFrame, sorted by (segment_id, timestamp)
    """
    logger.info("Running feature engineering pipeline …")
    df = traffic_df.copy()

    # Ensure correct sort order (critical for lags)
    df = df.sort_values(["segment_id", "timestamp"]).reset_index(drop=True)

    # 1. Temporal features
    df = build_temporal_features(df)
    logger.info("  ✓ Temporal features")

    # 2. Network-derived features
    df = build_network_features(df)
    logger.info("  ✓ Network features")

    # 3. Lag features
    df = build_lag_features(df)
    logger.info("  ✓ Lag features")

    # 4. Rolling statistics
    df = build_rolling_features(df)
    logger.info("  ✓ Rolling statistics")

    # 5. Incident features
    df = build_incident_features(df, incident_flags)
    logger.info("  ✓ Incident features")

    # 6. Roadwork features
    df = build_roadwork_features(df, roadwork_flags)
    logger.info("  ✓ Roadwork features")

    # 7. OD demand features
    df = build_od_demand_features(df, od_demand, network)
    logger.info("  ✓ OD demand features")

    feature_cols = get_feature_columns(df)
    logger.info("Total feature columns: %d", len(feature_cols))
    return df


def generate_feature_lineage() -> dict:
    """Return a machine-readable feature lineage dictionary."""
    return {
        "features": [
            {"name": "speed_kmh", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "flow_vph", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "occupancy_pct", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "congestion_index", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "delay_min", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "queue_length_veh", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "travel_time_min", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "free_flow_time_min", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "sensor_quality", "source": "traffic_train", "available_at": "t", "horizons": "all"},
            {"name": "hour, minute, day_of_week, …", "source": "timestamp", "available_at": "t", "horizons": "all"},
            {"name": "hour_sin, hour_cos, dow_sin, dow_cos", "source": "derived", "available_at": "t", "horizons": "all"},
            {"name": "is_weekend, is_peak, is_am_peak, is_pm_peak", "source": "derived", "available_at": "t", "horizons": "all"},
            {"name": "speed_kmh_lag_N, flow_vph_lag_N, …", "source": "traffic_train [t-N]", "available_at": "t", "horizons": "all"},
            {"name": "speed_kmh_roll_mean_Xmin, …", "source": "traffic_train [t-W:t]", "available_at": "t", "horizons": "all"},
            {"name": "lanes, capacity_vph, length_km, grade_pct, …", "source": "network.csv", "available_at": "always", "horizons": "all"},
            {"name": "structural_bottleneck, importance, peak_capacity_factor", "source": "network.csv", "available_at": "always", "horizons": "all"},
            {"name": "road_class_encoded, has_signal", "source": "derived from network.csv", "available_at": "always", "horizons": "all"},
            {"name": "capacity_utilization, delay_ratio, speed_ratio", "source": "derived", "available_at": "t", "horizons": "all"},
            {"name": "active_incident, incident_severity, incident_lanes_blocked", "source": "incidents_train [active at t]", "available_at": "t", "horizons": "all"},
            {"name": "active_roadwork, roadwork_closure_fraction", "source": "roadworks_train [active at t]", "available_at": "t", "horizons": "all"},
            {"name": "temperature_c, rain_intensity, event_level, holiday_flag", "source": "context_train", "available_at": "t", "horizons": "all"},
            {"name": "od_demand_pressure", "source": "od_demand_profiles.csv", "available_at": "always", "horizons": "all"},
            {"name": "target_speed_15m, target_flow_15m, …", "source": "forecast_targets_train", "available_at": "NEVER — labels only", "horizons": "EXCLUDED"},
        ]
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys
    sys.path.insert(0, r"d:\data-urban\traffic-intelligence")
    from ml.preprocessing.data_loader import build_merged_dataset, load_incidents, load_roadworks
    from ml.preprocessing.data_loader import get_incident_active_flags, get_roadwork_active_flags

    print("Loading data (small sample for speed test)…")
    features_df, targets_df = build_merged_dataset("train")

    # Use only first day for quick test
    cutoff = pd.Timestamp("2026-01-02")
    features_df = features_df[features_df["timestamp"] < cutoff].copy()

    incidents = load_incidents("train")
    roadworks = load_roadworks("train")
    inc_flags = get_incident_active_flags(features_df, incidents)
    rw_flags = get_roadwork_active_flags(features_df, roadworks)

    result = run_full_feature_pipeline(features_df, inc_flags, rw_flags)
    feature_cols = get_feature_columns(result)

    print(f"Shape after feature engineering: {result.shape}")
    print(f"Feature columns ({len(feature_cols)}): {feature_cols[:20]}…")
    print("NaN counts in features:")
    print(result[feature_cols].isnull().sum().sort_values(ascending=False).head(20))
    print("Done.")
