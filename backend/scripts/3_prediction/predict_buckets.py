#!/usr/bin/env python3
"""
Predict benefit buckets with current trained models (no retraining).

Reads:
- registry.json for feature order
- features.json for feature values (produced by calculate_features.py)

Writes:
- outputs_for_frontend.json
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent

TARGETS = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]


def resolve_models_dir() -> Path:
    preferred = SCRIPT_DIR / "models"
    if (preferred / "registry.json").exists():
        return preferred
    return DB_ROOT / "2_ml" / "artifacts" / "models"


def get_feature_columns(registry_path: Path) -> list[str]:
    """Feature order = keys of feature_importance from registry (training column order)."""
    with open(registry_path, "r") as f:
        registry = json.load(f)

    for name in TARGETS:
        if name in registry and "feature_importance" in registry[name]:
            cols = list(registry[name]["feature_importance"].keys())
            return cols
    return []


def load_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def build_X(features_dict: dict, feature_columns: list[str]) -> tuple[np.ndarray, list[str]]:
    """
    One row, same order as training.
    Missing/unparseable -> NaN, then impute with 0.
    Returns (X, missing_cols)
    """
    row = []
    missing = []

    for col in feature_columns:
        if col not in features_dict:
            missing.append(col)
            row.append(np.nan)
            continue

        v = features_dict.get(col)
        if v is None:
            missing.append(col)
            row.append(np.nan)
            continue

        try:
            row.append(float(v))
        except (TypeError, ValueError):
            missing.append(col)
            row.append(np.nan)

    X = np.array([row], dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    models_dir_default = resolve_models_dir()
    parser.add_argument("--models-dir", default=str(models_dir_default))
    parser.add_argument("--registry", default=str(Path(models_dir_default) / "registry.json"))
    parser.add_argument("--features", default=str(SCRIPT_DIR / "working_data" / "features.json"))
    parser.add_argument("--output", default=str(SCRIPT_DIR / "frontend_data" / "outputs_for_frontend.json"))
    parser.add_argument("--max-missing-frac", type=float, default=0.20, help="Fail if > this fraction of features are missing")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    registry_path = Path(args.registry)
    features_path = Path(args.features)
    output_path = Path(args.output)

    if not registry_path.exists():
        print(f"❌ Registry not found: {registry_path}")
        sys.exit(1)

    if not features_path.exists():
        print(f"❌ Features not found: {features_path}")
        print("Run first: calculate_features.py must write the features file you point to.")
        sys.exit(1)

    feature_columns = get_feature_columns(registry_path)
    if not feature_columns:
        print("❌ Could not read feature order from registry (feature_importance keys missing).")
        sys.exit(1)

    features_dict = load_json(features_path)
    X, missing_cols = build_X(features_dict, feature_columns)

    missing_frac = len(missing_cols) / max(1, len(feature_columns))
    print(f"📥 Loaded features: {features_path}")
    print(f"🔢 Model expects {len(feature_columns)} features")
    print(f"⚠️ Missing/unparseable: {len(missing_cols)} ({missing_frac:.1%})")
    if missing_cols:
        print("First missing cols:", missing_cols[:25])

    print("🧪 X nonzero count:", int(np.count_nonzero(X)))
    print("🧪 X min/max:", float(np.min(X)), float(np.max(X)))

    if missing_frac > args.max_missing_frac:
        print(
            f"❌ Too many missing features ({missing_frac:.1%}). "
            "Your calculate_features output keys likely don't match the registry feature names."
        )
        sys.exit(2)

    try:
        import joblib
    except ImportError:
        print("❌ joblib required: pip install joblib")
        sys.exit(1)

    predictions: dict[str, float | None] = {}
    for target in TARGETS:
        model_path = models_dir / f"{target}_model.joblib"
        if not model_path.exists():
            print(f"⚠️ Model not found: {model_path}")
            predictions[target] = None
            continue

        model = joblib.load(model_path)
        pred = model.predict(X)
        predictions[target] = float(pred[0])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(predictions, f, indent=2)

    print(f"✅ Predictions written to {output_path}")
    for k, v in predictions.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
