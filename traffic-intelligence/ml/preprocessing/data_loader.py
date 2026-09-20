"""
Data Loader and Preprocessing Pipeline
=======================================
Loads, cleans, and merges all dataset tables.
Handles: row shuffle, missing values, spikes, stuck sensors,
         impossible negative readings, duplicates.
"""

import os
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("TRAFFIC_DATA_DIR",
                               r"d:\data-urban\NEURAX_SMART_CITIES_TRAINING_V2"))


# ---------------------------------------------------------------------------
# Low-level loaders
# ---------------------------------------------------------------------------

def load_traffic(split: str = "train") -> pd.DataFrame:
    """Load and clean traffic observations (train or validation)."""
    path = DATA_DIR / f"traffic_{split}.csv"
    logger.info("Loading %s …", path)
    df = pd.read_csv(path, parse_dates=["timestamp"])

    # Sort — manifest warns of row shuffle
    df = df.sort_values(["segment_id", "timestamp"]).reset_index(drop=True)

    # Remove exact duplicates
    n_before = len(df)
    df = df.drop_duplicates(subset=["timestamp", "segment_id"], keep="first")
    if len(df) < n_before:
        logger.warning("Removed %d duplicate rows from traffic_%s", n_before - len(df), split)

    # Clip impossible negatives
    numeric_cols = ["speed_kmh", "flow_vph", "occupancy_pct",
                    "travel_time_min", "free_flow_time_min",
                    "delay_min", "queue_length_veh", "congestion_index"]
    for col in numeric_cols:
        if col in df.columns:
            neg_mask = df[col] < 0
            if neg_mask.any():
                logger.warning("Clipping %d negative values in %s", neg_mask.sum(), col)
                df.loc[neg_mask, col] = np.nan

    # Detect and null out stuck sensors (same value for 12+ consecutive steps per segment)
    dynamic_sensor_cols = ["speed_kmh", "flow_vph", "occupancy_pct", "congestion_index"]
    df = _remove_stuck_sensors(df, dynamic_sensor_cols, stuck_threshold=12)

    # Spike detection — IQR method, per segment
    df = _clip_spikes(df, ["speed_kmh", "flow_vph", "congestion_index"])

    # Fill remaining NaNs with forward-fill then backward-fill within segment
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df.groupby("segment_id")[col].transform(
                lambda x: x.ffill().bfill()
            )

    logger.info("Traffic %s loaded: %d rows, %d segments", split, len(df), df["segment_id"].nunique())
    return df


def _remove_stuck_sensors(df: pd.DataFrame, cols: list, stuck_threshold: int = 12) -> pd.DataFrame:
    """Null out values where a sensor reports the same reading for >= stuck_threshold steps."""
    for col in cols:
        if col not in df.columns:
            continue
        # Identify runs of identical values per segment
        df["_prev"] = df.groupby("segment_id")[col].shift(1)
        df["_same"] = (df[col] == df["_prev"])
        df["_run"] = df.groupby("segment_id")["_same"].transform(
            lambda x: x * (x.groupby((x != x.shift()).cumsum()).cumcount() + 1)
        )
        stuck_mask = df["_run"] >= stuck_threshold
        if stuck_mask.any():
            logger.warning("Nulling %d stuck-sensor values in %s", stuck_mask.sum(), col)
            df.loc[stuck_mask, col] = np.nan
    df = df.drop(columns=["_prev", "_same", "_run"], errors="ignore")
    return df


def _clip_spikes(df: pd.DataFrame, cols: list, iqr_factor: float = 5.0) -> pd.DataFrame:
    """Clip extreme spikes per segment using IQR method."""
    for col in cols:
        if col not in df.columns:
            continue
        q25 = df.groupby("segment_id")[col].transform(lambda x: x.quantile(0.25))
        q75 = df.groupby("segment_id")[col].transform(lambda x: x.quantile(0.75))
        iqr = q75 - q25
        lower = q25 - iqr_factor * iqr
        upper = q75 + iqr_factor * iqr
        spike_mask = (df[col] < lower) | (df[col] > upper)
        if spike_mask.any():
            logger.warning("Clipping %d spike values in %s", spike_mask.sum(), col)
            df[col] = df[col].clip(lower=lower, upper=upper)
    return df


def load_forecast_targets(split: str = "train") -> pd.DataFrame:
    """Load forecast target labels. NEVER used as features — labels only."""
    path = DATA_DIR / f"forecast_targets_{split}.csv"
    logger.info("Loading forecast targets from %s …", path)
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values(["segment_id", "timestamp"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["timestamp", "segment_id"], keep="first")
    logger.info("Forecast targets %s: %d rows", split, len(df))
    return df


def load_network() -> pd.DataFrame:
    """Load road network static attributes."""
    path = DATA_DIR / "network.csv"
    df = pd.read_csv(path)
    logger.info("Network: %d segments", len(df))
    return df


def load_nodes() -> pd.DataFrame:
    """Load node geographic coordinates."""
    path = DATA_DIR / "nodes.csv"
    df = pd.read_csv(path)
    logger.info("Nodes: %d nodes", len(df))
    return df


def load_incidents(split: str = "train") -> pd.DataFrame:
    """Load incident records."""
    path = DATA_DIR / f"incidents_{split}.csv"
    df = pd.read_csv(path, parse_dates=["start_time", "end_time"])
    logger.info("Incidents %s: %d records", split, len(df))
    return df


def load_roadworks(split: str = "train") -> pd.DataFrame:
    """Load roadwork records."""
    path = DATA_DIR / f"roadworks_{split}.csv"
    df = pd.read_csv(path, parse_dates=["start_time", "end_time"])
    logger.info("Roadworks %s: %d records", split, len(df))
    return df


def load_context(split: str = "train") -> pd.DataFrame:
    """Load context/weather/event records."""
    path = DATA_DIR / f"context_{split}.csv"
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    logger.info("Context %s: %d rows", split, len(df))
    return df


def load_signal_plans() -> pd.DataFrame:
    path = DATA_DIR / "signal_plans.csv"
    return pd.read_csv(path)


def load_od_demand() -> pd.DataFrame:
    path = DATA_DIR / "od_demand_profiles.csv"
    return pd.read_csv(path)


def load_planning_candidates() -> pd.DataFrame:
    path = DATA_DIR / "planning_candidates.csv"
    return pd.read_csv(path)


def load_turn_restrictions() -> pd.DataFrame:
    path = DATA_DIR / "turn_restrictions.csv"
    return pd.read_csv(path)


def load_scenario_examples() -> pd.DataFrame:
    path = DATA_DIR / "scenario_examples.csv"
    return pd.read_csv(path, parse_dates=["start_time", "end_time"])


# ---------------------------------------------------------------------------
# Merged dataset builder
# ---------------------------------------------------------------------------

def build_merged_dataset(split: str = "train") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build fully merged feature dataset + target labels.

    Returns:
        features_df: merged traffic + context (no target columns)
        targets_df:  forecast target labels aligned to same (timestamp, segment_id)
    """
    traffic = load_traffic(split)
    context = load_context(split)
    network = load_network()
    targets = load_forecast_targets(split)

    # Merge network static attributes onto traffic
    network_cols = ["segment_id", "road_class", "lanes", "free_flow_speed_kmh",
                    "capacity_vph", "length_km", "grade_pct", "structural_bottleneck",
                    "importance", "peak_capacity_factor", "signal_id",
                    "source_node", "target_node"]
    net_sub = network[[c for c in network_cols if c in network.columns]].copy()
    # Drop source_node/target_node from network as they already exist in traffic
    net_sub = net_sub.drop(columns=["source_node", "target_node"], errors="ignore")

    traffic = traffic.merge(net_sub, on="segment_id", how="left")

    # Merge context onto traffic by timestamp (forward-fill if 5-min aligned)
    context_cols = ["timestamp", "temperature_c", "rain_intensity",
                    "event_level", "holiday_flag"]
    ctx_sub = context[[c for c in context_cols if c in context.columns]].copy()
    traffic = pd.merge_asof(
        traffic.sort_values("timestamp"),
        ctx_sub.sort_values("timestamp"),
        on="timestamp",
        direction="backward"
    )
    traffic = traffic.sort_values(["segment_id", "timestamp"]).reset_index(drop=True)

    # Align targets
    targets_aligned = targets.merge(
        traffic[["timestamp", "segment_id"]],
        on=["timestamp", "segment_id"],
        how="inner"
    )

    logger.info("Merged dataset %s: %d rows", split, len(traffic))
    logger.info("Aligned targets: %d rows", len(targets_aligned))
    return traffic, targets_aligned


def get_incident_active_flags(traffic: pd.DataFrame,
                               incidents: pd.DataFrame) -> pd.DataFrame:
    """
    For each (timestamp, segment_id) in traffic, compute incident features.
    Returns a DataFrame with same index as traffic with incident columns.
    """
    result = traffic[["timestamp", "segment_id"]].copy()
    result["active_incident"] = 0
    result["incident_severity"] = 0
    result["incident_lanes_blocked"] = 0
    result["incident_type_encoded"] = 0

    type_map = {
        "stalled_vehicle": 1, "demand_surge": 2, "accident_like": 3,
        "road_closure": 4, "lane_blockage": 5
    }

    if incidents.empty:
        return result

    for _, inc in incidents.iterrows():
        mask = (
            (result["segment_id"] == inc["segment_id"]) &
            (result["timestamp"] >= inc["start_time"]) &
            (result["timestamp"] <= inc["end_time"])
        )
        result.loc[mask, "active_incident"] = 1
        result.loc[mask, "incident_severity"] = inc.get("severity", 1)
        result.loc[mask, "incident_lanes_blocked"] = inc.get("lanes_blocked", 0)
        result.loc[mask, "incident_type_encoded"] = type_map.get(
            inc.get("incident_type", ""), 0
        )
    return result


def get_roadwork_active_flags(traffic: pd.DataFrame,
                               roadworks: pd.DataFrame) -> pd.DataFrame:
    """
    For each (timestamp, segment_id), compute roadwork features.
    """
    result = traffic[["timestamp", "segment_id"]].copy()
    result["active_roadwork"] = 0
    result["roadwork_closure_fraction"] = 0.0

    work_type_map = {
        "lane_maintenance": 1, "resurfacing": 2, "emergency": 3
    }
    result["roadwork_type_encoded"] = 0

    if roadworks.empty:
        return result

    for _, rw in roadworks.iterrows():
        mask = (
            (result["segment_id"] == rw["segment_id"]) &
            (result["timestamp"] >= rw["start_time"]) &
            (result["timestamp"] <= rw["end_time"])
        )
        result.loc[mask, "active_roadwork"] = 1
        result.loc[mask, "roadwork_closure_fraction"] = rw.get("closure_fraction", 0.0)
        result.loc[mask, "roadwork_type_encoded"] = work_type_map.get(
            rw.get("work_type", ""), 0
        )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    print("Testing data_loader …")
    features, targets = build_merged_dataset("train")
    print(f"Features shape: {features.shape}")
    print(f"Targets shape:  {targets.shape}")
    print("Feature columns:", list(features.columns))
    print("Target columns:", [c for c in targets.columns if "target" in c])
    print("Done.")
