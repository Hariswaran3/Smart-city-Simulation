"""
Prediction Service
==================
Loads trained models and generates predictions for arbitrary inputs.
Also computes per-prediction explanations (feature importance + local contribution).
"""

import sys
import logging
import pickle
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

from ml.train import TARGET_COL_MAP, HORIZONS, TARGET_TYPES, load_model, PersistenceModel

# Congestion classification thresholds (based on congestion_index)
CONGESTION_LEVELS = {
    "free":     (0.0,   0.05),
    "moderate": (0.05,  0.15),
    "heavy":    (0.15,  0.30),
    "severe":   (0.30,  float("inf")),
}


def classify_congestion(congestion_index: float) -> str:
    """Convert numeric congestion_index to a severity label."""
    for level, (lo, hi) in CONGESTION_LEVELS.items():
        if lo <= congestion_index < hi:
            return level
    return "severe"


def congestion_color(congestion_index: float) -> str:
    """Return Leaflet-compatible color string."""
    level = classify_congestion(congestion_index)
    return {
        "free": "#22c55e",      # green
        "moderate": "#eab308",  # yellow
        "heavy": "#f97316",     # orange
        "severe": "#ef4444",    # red
    }.get(level, "#6b7280")     # gray default


class TrafficPredictor:
    """
    Unified predictor: loads models for all horizons and target types,
    generates predictions, confidence estimates, and feature explanations.
    """

    def __init__(self, feature_cols: List[str], prefer: str = "lgbm"):
        self.feature_cols = feature_cols
        self.prefer = prefer
        self.models: Dict[str, Any] = {}
        self._registry: Optional[dict] = None
        self._load_models()

    def _load_models(self):
        registry_path = MODELS_DIR / "model_registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                self._registry = json.load(f)

        for target_type in TARGET_TYPES:
            for horizon in HORIZONS:
                key = f"{target_type}_{horizon}"
                model = load_model(target_type, horizon, self.prefer)
                if model is not None:
                    # Patch for scikit-learn version mismatch where older models lack _preprocessor
                    if type(model).__name__ == "HistGradientBoostingRegressor" and not hasattr(model, "_preprocessor"):
                        model._preprocessor = None
                    self.models[key] = model
                    logger.debug("Loaded model: %s", key)
                else:
                    # Fallback to persistence
                    self.models[key] = PersistenceModel(target_type, horizon)
                    logger.debug("Using persistence for: %s", key)

    def predict_segment(self, segment_id: str, features_row: pd.DataFrame) -> dict:
        """
        Generate multi-horizon predictions for a single segment.

        Args:
            segment_id: road segment ID
            features_row: single-row DataFrame with all feature columns

        Returns:
            dict with predictions for all horizons and target types,
            plus congestion level, color, confidence, and top contributing features.
        """
        result = {
            "segment_id": segment_id,
            "horizons": {},
        }

        X = self._prepare_input(features_row)

        for target_type in TARGET_TYPES:
            for horizon in HORIZONS:
                key = f"{target_type}_{horizon}"
                model = self.models.get(key)
                if model is None:
                    continue

                if isinstance(model, PersistenceModel):
                    pred_val = float(model.predict(features_row)[0])
                    model_type = "persistence"
                    confidence = 0.5
                else:
                    pred_val = float(model.predict(X)[0])
                    model_type = type(model).__name__
                    confidence = self._estimate_confidence(model, X, target_type)

                h_key = f"+{horizon}"
                if h_key not in result["horizons"]:
                    result["horizons"][h_key] = {
                        "horizon": horizon,
                        "model_type": model_type,
                        "confidence": confidence,
                    }

                result["horizons"][h_key][target_type] = pred_val

                if target_type == "congestion":
                    result["horizons"][h_key]["congestion_level"] = classify_congestion(pred_val)
                    result["horizons"][h_key]["color"] = congestion_color(pred_val)

        # Top contributing features (explanation)
        result["explanation"] = self._explain(X)
        return result

    def predict_batch(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate predictions for all rows in features_df.
        Returns a wide DataFrame with all predicted columns.
        """
        X = self._prepare_input(features_df)
        preds = features_df[["timestamp", "segment_id"]].copy()

        for target_type in TARGET_TYPES:
            for horizon in HORIZONS:
                key = f"{target_type}_{horizon}"
                model = self.models.get(key)
                col_name = f"pred_{target_type}_{horizon}"
                if model is None:
                    preds[col_name] = np.nan
                    continue
                if isinstance(model, PersistenceModel):
                    preds[col_name] = model.predict(features_df)
                else:
                    preds[col_name] = model.predict(X)

        # Add congestion levels for each horizon
        for horizon in HORIZONS:
            col = f"pred_congestion_{horizon}"
            if col in preds.columns:
                preds[f"congestion_level_{horizon}"] = preds[col].apply(classify_congestion)
                preds[f"congestion_color_{horizon}"] = preds[col].apply(congestion_color)

        return preds

    def _prepare_input(self, df: pd.DataFrame) -> pd.DataFrame:
        """Align input to model feature columns, filling missing with 0."""
        available = [c for c in self.feature_cols if c in df.columns]
        missing = [c for c in self.feature_cols if c not in df.columns]
        X = df[available].copy()
        for col in missing:
            X[col] = 0.0
        X = X[self.feature_cols]
        # Fill NaN
        for col in self.feature_cols:
            if X[col].isnull().any():
                X[col] = X[col].fillna(0.0)
        return X

    def _estimate_confidence(self, model, X: pd.DataFrame, target_type: str) -> float:
        """
        Confidence proxy:
          - For tree ensembles: std of individual tree predictions normalized by mean range.
          - Falls back to 0.7 if not computable.
        Clearly documented as a proxy, not a calibrated probability.
        """
        try:
            if hasattr(model, "estimators_"):  # sklearn ensemble
                tree_preds = np.array([t.predict(X.values) for t in model.estimators_])
                std = tree_preds.std(axis=0).mean()
                mean_val = abs(tree_preds.mean())
                rel_std = std / (mean_val + 1e-6)
                confidence = float(max(0.3, min(0.95, 1.0 - rel_std * 2)))
                return confidence
            elif hasattr(model, "predict"):
                return 0.70  # LightGBM — fixed proxy
        except Exception:
            pass
        return 0.65

    def _explain(self, X: pd.DataFrame) -> dict:
        """
        Local feature contribution explanation.
        Uses model feature importance × feature value deviation from mean.
        Returns top contributing features with their scaled contribution.
        Note: this is a feature-importance approximation, not SHAP.
        """
        contributions = {}
        for target_type in TARGET_TYPES:
            key = f"{target_type}_15m"
            model = self.models.get(key)
            if model is None or isinstance(model, PersistenceModel):
                continue
            if not hasattr(model, "feature_importances_"):
                continue
            importances = model.feature_importances_
            vals = X.values[0] if len(X) == 1 else X.values.mean(axis=0)
            contrib = {
                col: float(imp * abs(val))
                for col, imp, val in zip(self.feature_cols, importances, vals)
                if imp > 0
            }
            top = dict(sorted(contrib.items(), key=lambda x: -x[1])[:10])
            contributions[target_type] = {
                "method": "feature_importance_x_magnitude (proxy, not SHAP)",
                "top_features": top
            }
        return contributions

    def get_current_state(self, features_df: pd.DataFrame, timestamp=None) -> pd.DataFrame:
        """Return the latest traffic state for all segments."""
        if timestamp is not None:
            state = features_df[features_df["timestamp"] == timestamp]
        else:
            state = features_df.loc[
                features_df.groupby("segment_id")["timestamp"].idxmax()
            ]
        return state

    def get_congestion_map(self, predictions: pd.DataFrame, horizon: str = "15m") -> list:
        """
        Return a list of segment congestion entries for map rendering.
        """
        col_congestion = f"pred_congestion_{horizon}"
        col_speed = f"pred_speed_{horizon}"
        col_flow = f"pred_flow_{horizon}"
        col_level = f"congestion_level_{horizon}"
        col_color = f"congestion_color_{horizon}"

        if col_congestion not in predictions.columns:
            return []

        result = []
        for _, row in predictions.iterrows():
            entry = {
                "segment_id": row["segment_id"],
                "congestion_index": float(row.get(col_congestion, 0)),
                "congestion_level": row.get(col_level, "free"),
                "color": row.get(col_color, "#22c55e"),
                "horizon": horizon,
            }
            if col_speed in predictions.columns:
                entry["speed_kmh"] = float(row.get(col_speed, 0))
            if col_flow in predictions.columns:
                entry["flow_vph"] = float(row.get(col_flow, 0))
            result.append(entry)
        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from ml.preprocessing.data_loader import (
        build_merged_dataset, load_incidents, load_roadworks,
        get_incident_active_flags, get_roadwork_active_flags,
        load_od_demand, load_network
    )
    from ml.features.feature_engineering import run_full_feature_pipeline, get_feature_columns

    logger.info("Loading validation data for prediction test …")
    features, targets = build_merged_dataset("validation")
    incidents = load_incidents("validation")
    roadworks = load_roadworks("validation")
    od = load_od_demand()
    net = load_network()
    inc_f = get_incident_active_flags(features, incidents)
    rw_f = get_roadwork_active_flags(features, roadworks)
    features = run_full_feature_pipeline(features, inc_f, rw_f, od, net)
    feature_cols = get_feature_columns(features)

    predictor = TrafficPredictor(feature_cols)
    logger.info("Models loaded: %s", list(predictor.models.keys()))

    # Test batch prediction
    sample = features.head(100)
    preds = predictor.predict_batch(sample)
    logger.info("Batch predictions shape: %s", preds.shape)
    logger.info("Sample predictions:\n%s", preds.head(3).to_string())

    # Test segment prediction
    seg_row = features[features["segment_id"] == "R0001"].head(1)
    result = predictor.predict_segment("R0001", seg_row)
    logger.info("Segment prediction:\n%s", json.dumps(result, indent=2, default=str))
