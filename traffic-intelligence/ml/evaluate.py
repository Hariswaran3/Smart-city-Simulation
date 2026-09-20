"""
Model Evaluation — Validation-Set Assessment
=============================================
Evaluates trained models against the validation split.
Produces per-horizon, per-segment-class, and peak/non-peak breakdowns.
Never uses validation targets during training.
"""

import sys
import json
import logging
import pickle
import warnings
from pathlib import Path
from typing import Dict, Optional, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

from ml.train import (
    TARGET_COL_MAP, HORIZONS, TARGET_TYPES,
    compute_metrics, load_model, PersistenceModel
)


def evaluate_all(
    val_features: pd.DataFrame,
    val_targets: pd.DataFrame,
    feature_cols: List[str],
) -> dict:
    """
    Evaluate all model variants on validation data.
    Returns nested dict: {target_type: {horizon: {model: metrics}}}
    """
    results = {}

    for target_type in TARGET_TYPES:
        results[target_type] = {}
        for horizon in HORIZONS:
            target_col = TARGET_COL_MAP[(target_type, horizon)]
            if target_col not in val_targets.columns:
                continue

            logger.info("Evaluating: %s @ +%s", target_type, horizon)

            # Prepare validation set
            merged = val_features[["timestamp", "segment_id"] + feature_cols].merge(
                val_targets[["timestamp", "segment_id", target_col]],
                on=["timestamp", "segment_id"],
                how="inner"
            ).dropna(subset=[target_col])

            if len(merged) == 0:
                logger.warning("No validation data for %s %s", target_type, horizon)
                continue

            X_val = merged[feature_cols].copy()
            for col in feature_cols:
                if X_val[col].isnull().any():
                    X_val[col] = X_val[col].fillna(X_val[col].median())
            y_val = merged[target_col].values

            horizon_results = {}

            # Persistence baseline
            pers = PersistenceModel(target_type, horizon)
            pers_pred = pers.predict(merged)
            horizon_results["persistence"] = compute_metrics(y_val, pers_pred, f"Persistence {target_type}@{horizon}")

            # LightGBM
            lgbm = load_model(target_type, horizon, "lgbm")
            if lgbm is not None:
                pred = lgbm.predict(X_val)
                horizon_results["lightgbm"] = compute_metrics(y_val, pred, f"LightGBM {target_type}@{horizon}")

                # Sub-group analysis
                if "is_peak" in merged.columns:
                    peak_mask = merged["is_peak"].values == 1
                    if peak_mask.sum() > 0:
                        horizon_results["lightgbm_peak"] = compute_metrics(
                            y_val[peak_mask], pred[peak_mask], f"  peak"
                        )
                    if (~peak_mask).sum() > 0:
                        horizon_results["lightgbm_offpeak"] = compute_metrics(
                            y_val[~peak_mask], pred[~peak_mask], f"  off-peak"
                        )

                if "active_incident" in merged.columns:
                    inc_mask = merged["active_incident"].values == 1
                    if inc_mask.sum() > 0:
                        horizon_results["lightgbm_incident"] = compute_metrics(
                            y_val[inc_mask], pred[inc_mask], f"  incident"
                        )

                if "road_class_encoded" in merged.columns:
                    for rc, rc_name in [(0, "collector"), (1, "arterial")]:
                        rc_mask = merged["road_class_encoded"].values == rc
                        if rc_mask.sum() > 0:
                            horizon_results[f"lightgbm_{rc_name}"] = compute_metrics(
                                y_val[rc_mask], pred[rc_mask], f"  {rc_name}"
                            )

            # ExtraTrees
            rf = load_model(target_type, horizon, "rf")
            if rf is not None:
                pred_rf = rf.predict(X_val)
                horizon_results["extratrees"] = compute_metrics(y_val, pred_rf, f"ExtraTrees {target_type}@{horizon}")

            results[target_type][horizon] = horizon_results

    return results


def format_report(results: dict) -> str:
    """Format evaluation results as a readable Markdown table."""
    lines = ["# Model Evaluation Report — Validation Set\n"]
    lines.append("## Per-Horizon Results\n")

    for target_type in TARGET_TYPES:
        lines.append(f"### {target_type.upper()}\n")
        lines.append("| Horizon | Model | MAE | RMSE | R² | MAPE |")
        lines.append("|---------|-------|-----|------|----|------|")
        for horizon in HORIZONS:
            if target_type not in results or horizon not in results[target_type]:
                continue
            for model_name, m in results[target_type][horizon].items():
                if "_" in model_name and any(x in model_name for x in ["peak", "offpeak", "incident", "collector", "arterial"]):
                    continue
                mape_str = f"{m['mape']:.2f}%" if "mape" in m else "N/A"
                lines.append(f"| +{horizon} | {model_name} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['r2']:.4f} | {mape_str} |")
        lines.append("")

    lines.append("## Sub-Group Analysis (LightGBM)\n")
    for target_type in TARGET_TYPES:
        lines.append(f"### {target_type.upper()}\n")
        for horizon in HORIZONS:
            if target_type not in results or horizon not in results[target_type]:
                continue
            h_results = results[target_type][horizon]
            sub_keys = [k for k in h_results if "lightgbm_" in k]
            if sub_keys:
                lines.append(f"**+{horizon}**")
                lines.append("| Subgroup | MAE | RMSE | R² |")
                lines.append("|----------|-----|------|-----|")
                for k in sub_keys:
                    m = h_results[k]
                    subgroup = k.replace("lightgbm_", "")
                    lines.append(f"| {subgroup} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['r2']:.4f} |")
                lines.append("")

    return "\n".join(lines)


def run_evaluation(
    val_features: pd.DataFrame,
    val_targets: pd.DataFrame,
    feature_cols: List[str],
) -> dict:
    """Run full evaluation and save reports."""
    logger.info("Running validation evaluation …")
    results = evaluate_all(val_features, val_targets, feature_cols)

    # Save JSON
    json_path = REPORTS_DIR / "evaluation_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved: %s", json_path)

    # Save Markdown
    md_path = REPORTS_DIR / "evaluation_results.md"
    report = format_report(results)
    with open(md_path, "w") as f:
        f.write(report)
    logger.info("Saved: %s", md_path)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from ml.preprocessing.data_loader import (
        build_merged_dataset, load_incidents, load_roadworks,
        get_incident_active_flags, get_roadwork_active_flags,
        load_od_demand, load_network
    )
    from ml.features.feature_engineering import run_full_feature_pipeline, get_feature_columns

    logger.info("Loading validation data …")
    val_features, val_targets = build_merged_dataset("validation")
    incidents = load_incidents("validation")
    roadworks = load_roadworks("validation")
    od_demand = load_od_demand()
    network = load_network()

    inc_flags = get_incident_active_flags(val_features, incidents)
    rw_flags = get_roadwork_active_flags(val_features, roadworks)
    val_features = run_full_feature_pipeline(val_features, inc_flags, rw_flags, od_demand, network)
    feature_cols = get_feature_columns(val_features)

    results = run_evaluation(val_features, val_targets, feature_cols)
    logger.info("Evaluation complete.")
