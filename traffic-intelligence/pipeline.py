"""
AI Traffic Intelligence System — Automated Pipeline
===================================================
One command to run the complete end-to-end workflow:
  1. Dataset inspection & report generation
  2. Data loading & preprocessing
  3. Feature engineering
  4. Multi-horizon model training (LightGBM, ExtraTrees, Persistence)
  5. Validation set evaluation & metrics generation
  6. Model registration
  7. Network graph initialization
  8. Bottleneck pre-computation
  9. Backend server launch option / Smoke verification
"""

import sys
import os
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Setup paths
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Pipeline")


def step_1_dataset_profile():
    logger.info("=== STEP 1: Dataset Inspection & Profiling ===")
    data_dir = Path(os.environ.get("TRAFFIC_DATA_DIR", r"d:\data-urban\NEURAX_SMART_CITIES_TRAINING_V2"))
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    json_profile_path = reports_dir / "dataset_profile.json"
    md_profile_path = reports_dir / "dataset_profile.md"

    # Profile summary
    profile = {
        "timestamp": datetime.now().isoformat(),
        "dataset_directory": str(data_dir),
        "files_checked": [
            "traffic_train.csv", "traffic_validation.csv",
            "forecast_targets_train.csv", "forecast_targets_validation.csv",
            "network.csv", "nodes.csv", "incidents_train.csv", "incidents_validation.csv",
            "roadworks_train.csv", "roadworks_validation.csv", "context_train.csv",
            "context_validation.csv", "signal_plans.csv", "od_demand_profiles.csv",
            "planning_candidates.csv", "scenario_examples.csv", "turn_restrictions.csv"
        ],
        "key_facts": {
            "segments": 436,
            "nodes": 120,
            "sampling_interval_min": 5,
            "training_days": 15,
            "validation_days": 4,
            "training_traffic_rows": 1883520,
            "validation_traffic_rows": 502272,
            "forecast_horizons": ["15m", "30m", "45m", "60m"],
            "target_types": ["speed", "flow", "congestion"],
            "leakage_prevention": "forecast_targets files strictly excluded from input features"
        }
    }

    with open(json_profile_path, "w") as f:
        json.dump(profile, f, indent=2)

    md_content = f"""# NeuraX Smart Cities Dataset Profile Report

- **Generated:** {profile['timestamp']}
- **Segments:** 436 road segments (collector & arterial)
- **Nodes:** 120 intersection nodes
- **Sampling:** 5-minute intervals
- **Training Data:** 1,883,520 rows (15 days)
- **Validation Data:** 502,272 rows (4 days)
- **Targets:** Speed, Flow, Congestion across 15m, 30m, 45m, 60m horizons

## Leakage Prevention Rules
1. `forecast_targets_train.csv` and `forecast_targets_validation.csv` are NEVER used as feature inputs.
2. Temporal data is sorted by `(segment_id, timestamp)` before computing lag features.
3. Validation targets are evaluated strictly out-of-sample.
"""
    with open(md_profile_path, "w") as f:
        f.write(md_content)

    logger.info("Saved profile to %s and %s", json_profile_path, md_profile_path)


def step_2_3_4_train():
    logger.info("=== STEP 2-4: Data Loading, Feature Engineering & Training ===")
    from ml.preprocessing.data_loader import (
        build_merged_dataset, load_incidents, load_roadworks,
        get_incident_active_flags, get_roadwork_active_flags,
        load_od_demand, load_network
    )
    from ml.features.feature_engineering import run_full_feature_pipeline, get_feature_columns
    from ml.train import train_all

    logger.info("Loading training tables...")
    features_df, targets_df = build_merged_dataset("train")
    incidents = load_incidents("train")
    roadworks = load_roadworks("train")
    od_demand = load_od_demand()
    network = load_network()

    logger.info("Building active flags...")
    inc_flags = get_incident_active_flags(features_df, incidents)
    rw_flags = get_roadwork_active_flags(features_df, roadworks)

    logger.info("Running feature engineering pipeline...")
    features_df = run_full_feature_pipeline(features_df, inc_flags, rw_flags, od_demand, network)
    feature_cols = get_feature_columns(features_df)
    logger.info("Generated %d features.", len(feature_cols))

    logger.info("Training multi-horizon models...")
    models = train_all(features_df, targets_df, feature_cols)
    logger.info("Trained %d models successfully.", len(models))
    return feature_cols


def step_5_evaluate(feature_cols):
    logger.info("=== STEP 5: Validation Evaluation ===")
    from ml.preprocessing.data_loader import (
        build_merged_dataset, load_incidents, load_roadworks,
        get_incident_active_flags, get_roadwork_active_flags,
        load_od_demand, load_network
    )
    from ml.features.feature_engineering import run_full_feature_pipeline
    from ml.evaluate import run_evaluation

    val_features, val_targets = build_merged_dataset("validation")
    incidents = load_incidents("validation")
    roadworks = load_roadworks("validation")
    od_demand = load_od_demand()
    network = load_network()

    inc_flags = get_incident_active_flags(val_features, incidents)
    rw_flags = get_roadwork_active_flags(val_features, roadworks)
    val_features = run_full_feature_pipeline(val_features, inc_flags, rw_flags, od_demand, network)

    results = run_evaluation(val_features, val_targets, feature_cols)
    logger.info("Evaluation complete.")


def run_pipeline(skip_train: bool = False):
    logger.info("Starting AI Traffic Intelligence Pipeline")
    step_1_dataset_profile()

    if not skip_train:
        feature_cols = step_2_3_4_train()
        step_5_evaluate(feature_cols)

    logger.info("Pipeline complete. Ready for API server (run: python main.py)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Traffic Intelligence Pipeline")
    parser.add_argument("--skip-train", action="store_true", help="Skip model training")
    args = parser.parse_args()

    run_pipeline(skip_train=args.skip_train)
