#!/usr/bin/env python3
"""
Predict benefit buckets with current trained models (no retraining).
====================================================================

Uses existing coefficients from 2_ml/artifacts/models/:
- peak_shaving_benefit_model.joblib
- energy_procurement_optimization_model.joblib
- trading_revenue_model.joblib

Feature order is taken from registry.json (feature_importance keys = training column order).
Reads working_data/features.json (from calculate_features.py), builds X in that order,
imputes missing values (median), predicts each target, writes frontend_data/outputs_for_frontend.json.

Usage (from DB root or 3_prediction):
  python 3_prediction/calculate_features.py   # once: build features from frontend_data
  python 3_prediction/predict_buckets.py     # predict and write outputs_for_frontend.json
"""
from pathlib import Path
import json
import sys

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent

# Models: prefer 3_prediction/models (if you copied them), else 2_ml/artifacts/models
MODELS_DIR = SCRIPT_DIR / "models" if (SCRIPT_DIR / "models" / "registry.json").exists() else DB_ROOT / "2_ml" / "artifacts" / "models"
WORKING_FEATURES = SCRIPT_DIR / "working_data" / "features.json"
OUTPUT_JSON = SCRIPT_DIR / "frontend_data" / "outputs_for_frontend.json"

TARGETS = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]


def get_feature_columns(registry_path: Path) -> list[str]:
    """Feature order = keys of feature_importance from registry (same as training X.columns)."""
    with open(registry_path, "r") as f:
        registry = json.load(f)
    # Any of the three models has the same feature list
    for name in TARGETS:
        if name in registry and "feature_importance" in registry[name]:
            return list(registry[name]["feature_importance"].keys())
    return []


def load_features_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def build_X(features_dict: dict, feature_columns: list[str]) -> np.ndarray:
    """One row, same order as training. Missing → NaN, then impute with 0 (simple)."""
    row = []
    for col in feature_columns:
        v = features_dict.get(col)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            row.append(np.nan)
        else:
            try:
                row.append(float(v))
            except (TypeError, ValueError):
                row.append(np.nan)
    X = np.array([row], dtype=np.float64)
    # Impute NaN with 0 (training uses median; we don't have training median here)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X


def main() -> None:
    registry_path = MODELS_DIR / "registry.json"
    if not registry_path.exists():
        print(f"Registry not found: {registry_path}")
        print("Train models first: python 2_ml/2_train_models.py")
        sys.exit(1)

    if not WORKING_FEATURES.exists():
        print(f"Features not found: {WORKING_FEATURES}")
        print("Run first: python 3_prediction/calculate_features.py")
        sys.exit(1)

    feature_columns = get_feature_columns(registry_path)
    if not feature_columns:
        print("Could not read feature order from registry.")
        sys.exit(1)

    features_dict = load_features_json(WORKING_FEATURES)
    X = build_X(features_dict, feature_columns)

    try:
        import joblib
    except ImportError:
        print("joblib required: pip install joblib")
        sys.exit(1)

    predictions = {}
    for target in TARGETS:
        model_path = MODELS_DIR / f"{target}_model.joblib"
        if not model_path.exists():
            print(f"Model not found: {model_path}")
            predictions[target] = None
            continue
        model = joblib.load(model_path)
        pred = model.predict(X)
        predictions[target] = float(pred[0])

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(predictions, f, indent=2)

    print(f"Predictions written to {OUTPUT_JSON}")
    for k, v in predictions.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
