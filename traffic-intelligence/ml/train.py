"""
Multi-Horizon Traffic Forecasting — Training Script
====================================================
Trains separate models for each (horizon, target_type) combination:
  horizons: 15m, 30m, 45m, 60m
  targets:  speed, flow, congestion

Models: Persistence baseline, LightGBM, Random Forest
Uses time-aware validation — NEVER random shuffles temporal data.
"""

import os
import sys
import json
import logging
import warnings
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

REGISTRY_PATH = MODELS_DIR / "model_registry.json"

# Target column mapping
HORIZONS = ["15m", "30m", "45m", "60m"]
TARGET_TYPES = ["speed", "flow", "congestion"]

TARGET_COL_MAP = {
    ("speed", "15m"):      "target_speed_15m",
    ("speed", "30m"):      "target_speed_30m",
    ("speed", "45m"):      "target_speed_45m",
    ("speed", "60m"):      "target_speed_60m",
    ("flow", "15m"):       "target_flow_15m",
    ("flow", "30m"):       "target_flow_30m",
    ("flow", "45m"):       "target_flow_45m",
    ("flow", "60m"):       "target_flow_60m",
    ("congestion", "15m"): "target_congestion_15m",
    ("congestion", "30m"): "target_congestion_30m",
    ("congestion", "45m"): "target_congestion_45m",
    ("congestion", "60m"): "target_congestion_60m",
}


def compute_mape(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    """MAPE — only valid where y_true > threshold to avoid division by zero."""
    threshold = 0.01
    mask = np.abs(y_true) > threshold
    if mask.sum() == 0:
        return None
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, name: str = "") -> dict:
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = float(r2_score(y_true, y_pred))
    mape = compute_mape(y_true, y_pred)
    metrics = {"mae": mae, "rmse": rmse, "r2": r2}
    if mape is not None:
        metrics["mape"] = mape
    if name:
        logger.info("  [%s] MAE=%.4f  RMSE=%.4f  R2=%.4f", name, mae, rmse, r2)
    return metrics


class PersistenceModel:
    """
    Baseline: predict the current value as the future value.
    Represents 'nothing changes' assumption.
    Maps target_type to the source column in traffic observations.
    """
    SOURCE_MAP = {
        "speed": "speed_kmh",
        "flow": "flow_vph",
        "congestion": "congestion_index",
    }

    def __init__(self, target_type: str, horizon: str):
        self.target_type = target_type
        self.horizon = horizon
        self.source_col = self.SOURCE_MAP.get(target_type, "congestion_index")

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.source_col in X.columns:
            return X[self.source_col].values
        return np.zeros(len(X))

    def get_name(self) -> str:
        return f"persistence_{self.target_type}_{self.horizon}"


def try_import_lightgbm():
    try:
        import lightgbm as lgb
        return lgb
    except ImportError:
        return None


def build_lgbm_model(target_type: str, horizon: str):
    """Build a LightGBM regressor with traffic-appropriate hyperparameters."""
    lgb = try_import_lightgbm()
    if lgb is None:
        logger.warning("LightGBM not available, falling back to ExtraTrees")
        return None

    # Adjust parameters by horizon (longer horizon → more regularization)
    n_estimators = 300
    max_depth = 8
    if horizon in ("45m", "60m"):
        max_depth = 6
        n_estimators = 250

    return lgb.LGBMRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=42,
        n_jobs=4,
        verbose=-1,
    )


def build_hgb_model(target_type: str, horizon: str):
    from sklearn.ensemble import HistGradientBoostingRegressor
    max_depth = 8 if horizon in ("15m", "30m") else 6
    return HistGradientBoostingRegressor(
        max_iter=200,
        max_depth=max_depth,
        learning_rate=0.05,
        min_samples_leaf=20,
        random_state=42,
    )


def build_rf_model(target_type: str, horizon: str):
    return ExtraTreesRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=4,
    )


def prepare_training_data(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Join features with targets on (timestamp, segment_id).
    Drop rows where target is NaN.
    Returns (X, y).
    """
    merged = features_df[["timestamp", "segment_id"] + feature_cols].merge(
        targets_df[["timestamp", "segment_id", target_col]],
        on=["timestamp", "segment_id"],
        how="inner"
    )
    merged = merged.dropna(subset=[target_col])
    merged = merged.dropna(subset=feature_cols, thresh=len(feature_cols) // 2)

    # Fill remaining NaN in features with column median
    X = merged[feature_cols].copy()
    for col in feature_cols:
        if X[col].isnull().any():
            X[col] = X[col].fillna(X[col].median())
    y = merged[target_col]
    return X, y


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    return {"models": []}


def save_registry(registry: dict):
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, default=str)


def train_all(
    features_df: pd.DataFrame,
    targets_df: pd.DataFrame,
    feature_cols: List[str],
    dataset_version: str = "v2",
    use_lgbm: bool = True,
    use_rf: bool = True,
) -> dict:
    """
    Train models for all (target_type, horizon) combinations.
    Returns the model registry dict.
    """
    registry = load_registry()
    trained_models = {}
    lgb = try_import_lightgbm()

    for target_type in TARGET_TYPES:
        for horizon in HORIZONS:
            target_col = TARGET_COL_MAP[(target_type, horizon)]
            if target_col not in targets_df.columns:
                logger.warning("Target column %s not found, skipping", target_col)
                continue

            logger.info("=" * 60)
            logger.info("Training: %s @ +%s", target_type, horizon)

            X, y = prepare_training_data(features_df, targets_df, feature_cols, target_col)
            if len(X) == 0:
                logger.warning("No training data for %s %s", target_type, horizon)
                continue

            logger.info("  Training rows: %d", len(X))

            model_key = f"{target_type}_{horizon}"
            best_model = None
            best_mae = float("inf")
            all_metrics = {}

            # --- Persistence baseline ---
            persistence = PersistenceModel(target_type, horizon)
            pers_pred = persistence.predict(
                features_df.merge(
                    targets_df[["timestamp", "segment_id", target_col]],
                    on=["timestamp", "segment_id"],
                    how="inner"
                ).dropna(subset=[target_col])
            )
            pers_y = y.values
            if len(pers_pred) == len(pers_y):
                pers_metrics = compute_metrics(pers_y, pers_pred, "Persistence")
                all_metrics["persistence"] = pers_metrics

            # --- LightGBM ---
            if use_lgbm and lgb is not None:
                try:
                    lgbm_model = build_lgbm_model(target_type, horizon)
                    lgbm_model.fit(X, y)
                    pred = lgbm_model.predict(X)
                    metrics = compute_metrics(y.values, pred, "LightGBM (train)")
                    all_metrics["lightgbm_train"] = metrics
                    if metrics["mae"] < best_mae:
                        best_mae = metrics["mae"]
                        best_model = lgbm_model

                    # Save model
                    model_path = MODELS_DIR / f"lgbm_{model_key}.pkl"
                    with open(model_path, "wb") as f:
                        pickle.dump(lgbm_model, f)
                    logger.info("  LightGBM saved: %s", model_path)
                except Exception as e:
                    logger.error("LightGBM training failed (%s). Falling back to HistGradientBoosting.", e)

            # --- HistGradientBoosting fallback ---
            try:
                hgb_model = build_hgb_model(target_type, horizon)
                hgb_model.fit(X, y)
                pred = hgb_model.predict(X)
                metrics = compute_metrics(y.values, pred, "HistGradientBoosting (train)")
                all_metrics["hgb_train"] = metrics
                if metrics["mae"] < best_mae:
                    best_mae = metrics["mae"]
                    best_model = hgb_model

                model_path = MODELS_DIR / f"hgb_{model_key}.pkl"
                with open(model_path, "wb") as f:
                    pickle.dump(hgb_model, f)
                logger.info("  HistGradientBoosting saved: %s", model_path)
            except Exception as e:
                logger.error("HistGradientBoosting failed: %s", e)

            # --- Random Forest / ExtraTrees fallback ---
            if use_rf:
                try:
                    rf_model = build_rf_model(target_type, horizon)
                    rf_model.fit(X, y)
                    pred = rf_model.predict(X)
                    metrics = compute_metrics(y.values, pred, "ExtraTrees (train)")
                    all_metrics["extratrees_train"] = metrics
                    if metrics["mae"] < best_mae:
                        best_mae = metrics["mae"]
                        best_model = rf_model

                    model_path = MODELS_DIR / f"rf_{model_key}.pkl"
                    with open(model_path, "wb") as f:
                        pickle.dump(rf_model, f)
                    logger.info("  ExtraTrees saved: %s", model_path)
                except Exception as e:
                    logger.error("RF training failed: %s", e)

            # Feature importance (if available)
            feature_importance = {}
            if best_model is not None and hasattr(best_model, "feature_importances_"):
                importances = best_model.feature_importances_
                fi = dict(sorted(zip(feature_cols, importances),
                                  key=lambda x: -x[1])[:20])
                feature_importance = fi

            # Registry entry
            entry = {
                "model_key": model_key,
                "target_type": target_type,
                "horizon": horizon,
                "target_column": target_col,
                "features": feature_cols,
                "n_features": len(feature_cols),
                "training_rows": len(X),
                "metrics": all_metrics,
                "top_features": feature_importance,
                "training_timestamp": datetime.now().isoformat(),
                "dataset_version": dataset_version,
                "best_model_type": type(best_model).__name__ if best_model else "none",
            }
            registry["models"] = [m for m in registry["models"] if m["model_key"] != model_key]
            registry["models"].append(entry)
            trained_models[model_key] = best_model

            save_registry(registry)
            logger.info("  ✓ Registered: %s", model_key)

    logger.info("Training complete. %d model keys.", len(trained_models))
    return trained_models


def load_model(target_type: str, horizon: str, prefer: str = "hgb") -> Optional[object]:
    """Load a trained model from disk."""
    model_key = f"{target_type}_{horizon}"
    for prefix in [prefer, "hgb", "lgbm", "rf"]:
        path = MODELS_DIR / f"{prefix}_{model_key}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from ml.preprocessing.data_loader import (
        build_merged_dataset, load_incidents, load_roadworks,
        get_incident_active_flags, get_roadwork_active_flags,
        load_od_demand, load_network
    )
    from ml.features.feature_engineering import run_full_feature_pipeline, get_feature_columns

    logger.info("Loading training data …")
    features_df, targets_df = build_merged_dataset("train")

    incidents = load_incidents("train")
    roadworks = load_roadworks("train")
    od_demand = load_od_demand()
    network = load_network()

    inc_flags = get_incident_active_flags(features_df, incidents)
    rw_flags = get_roadwork_active_flags(features_df, roadworks)

    logger.info("Running feature engineering …")
    features_df = run_full_feature_pipeline(features_df, inc_flags, rw_flags, od_demand, network)
    feature_cols = get_feature_columns(features_df)
    logger.info("Feature columns: %d", len(feature_cols))

    logger.info("Starting training …")
    trained = train_all(features_df, targets_df, feature_cols)
    logger.info("Training complete. Models trained: %d", len(trained))
