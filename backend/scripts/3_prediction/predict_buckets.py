#!/usr/bin/env python3
"""
Predict benefit buckets with current trained models (no retraining).
====================================================================

Uses existing coefficients from 2_ml/artifacts/models/ (or 3_prediction/models/):
- peak_shaving_benefit_model.joblib
- energy_procurement_optimization_model.joblib
- trading_revenue_model.joblib

Feature order is taken from registry.json (feature_importance keys = training column order).
Reads working_data/features.json (from calculate_features.py), builds X in that order,
imputes missing values (0), predicts each target, writes frontend_data/outputs_for_frontend.json.

Usage (from DB root or 3_prediction):
  python 3_prediction/calculate_features.py   # once: build features from frontend_data
  python 3_prediction/predict_buckets.py       # predict and write outputs_for_frontend.json
  python 3_prediction/predict_buckets.py --debug   # same + write prediction_debug.json
"""
from pathlib import Path
import argparse
import json
import sys

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent

# Models: prefer 3_prediction/models (if you copied them), else 2_ml/artifacts/models
MODELS_DIR = SCRIPT_DIR / "models" if (SCRIPT_DIR / "models" / "registry.json").exists() else DB_ROOT / "2_ml" / "artifacts" / "models"
WORKING_FEATURES = SCRIPT_DIR / "working_data" / "features.json"
OUTPUT_JSON = SCRIPT_DIR / "frontend_data" / "outputs_for_frontend.json"
DEBUG_JSON = SCRIPT_DIR / "frontend_data" / "prediction_debug.json"

TARGETS = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]


def get_feature_columns(registry_path: Path) -> list[str]:
    """Feature order = keys of feature_importance from registry (same as training X.columns)."""
    with open(registry_path, "r") as f:
        registry = json.load(f)
    for name in TARGETS:
        if name in registry and "feature_importance" in registry[name]:
            return list(registry[name]["feature_importance"].keys())
    return []


def load_features_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def build_X(features_dict: dict, feature_columns: list[str]):
    """
    One row, same order as training. Fehlende Werte bleiben „leer“ (werden nur fürs Modell mit 0 gefüllt).
    Returns (X_df, row_debug): X_df für sklearn, row_debug mit source "from_features" | "imputed"
    (imputed = war leer in features.json).
    """
    row = []
    row_debug = []
    for col in feature_columns:
        v = features_dict.get(col)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            row.append(np.nan)
            row_debug.append({"name": col, "value": 0.0, "source": "imputed", "value_in_features": None})
        else:
            try:
                x = float(v)
                row.append(x)
                row_debug.append({"name": col, "value": x, "source": "from_features", "value_in_features": x})
            except (TypeError, ValueError):
                row.append(np.nan)
                row_debug.append({"name": col, "value": 0.0, "source": "imputed", "value_in_features": None})
    arr = np.array([row], dtype=np.float64)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    for i, d in enumerate(row_debug):
        d["value"] = float(arr[0, i])
    X_df = pd.DataFrame(arr, columns=feature_columns)
    return X_df, row_debug


def build_debug(
    registry: dict,
    feature_columns: list[str],
    row_debug: list[dict],
    predictions: dict,
    models_dir: Path,
) -> dict:
    """Build debug payload: feature count, source, importance per target, top features."""
    n_total = len(feature_columns)
    n_from_features = sum(1 for d in row_debug if d["source"] == "from_features")
    n_imputed = n_total - n_from_features

    empty_feature_names = [d["name"] for d in row_debug if d["source"] == "imputed"]
    # Per-feature: value, source, importance; bei imputed: value_in_features = null (leer)
    features_detail = []
    for d in row_debug:
        name = d["name"]
        rec = {
            "name": name,
            "value_used": d["value"],
            "source": d["source"],
            "was_empty": d["source"] == "imputed",
            "value_in_features": d.get("value_in_features"),
        }
        for target in TARGETS:
            if target in registry and "feature_importance" in registry[target]:
                imp = registry[target]["feature_importance"].get(name)
                rec[f"importance_{target}"] = round(float(imp), 6) if imp is not None else None
        features_detail.append(rec)

    # Top N by importance per target (for quick read)
    top_n = 15
    top_per_target = {}
    for target in TARGETS:
        if target not in registry or "feature_importance" not in registry[target]:
            continue
        imp = registry[target]["feature_importance"]
        sorted_names = sorted(imp.keys(), key=lambda k: imp[k], reverse=True)
        top_per_target[target] = [
            {
                "rank": i + 1,
                "name": name,
                "importance": round(imp[name], 6),
                "value_used": next((d["value"] for d in row_debug if d["name"] == name), None),
                "source": next((d["source"] for d in row_debug if d["name"] == name), None),
            }
            for i, name in enumerate(sorted_names[:top_n])
        ]

    return {
        "summary": {
            "n_features_used": n_total,
            "n_from_features_json": n_from_features,
            "n_imputed": n_imputed,
            "features_json_path": str(WORKING_FEATURES),
            "models_dir": str(models_dir),
        },
        "empty_feature_names": empty_feature_names,
        "predictions": predictions,
        "features_detail": features_detail,
        "top_features_per_target": top_per_target,
    }


def print_debug_to_terminal(debug_payload: dict) -> None:
    """Print debug summary and top features per target to terminal."""
    s = debug_payload["summary"]
    print()
    print("--- Debug ---")
    print(f"Features: {s['n_features_used']} total  |  from features.json: {s['n_from_features_json']}  |  imputed: {s['n_imputed']}")
    print(f"features.json: {s['features_json_path']}")
    print(f"models: {s['models_dir']}")
    print()
    print("Predictions:")
    for k, v in debug_payload["predictions"].items():
        print(f"  {k}: {v}")
    top = debug_payload.get("top_features_per_target", {})
    for target in TARGETS:
        if target not in top:
            continue
        print()
        print(f"--- Top features for {target} (by importance) ---")
        for r in top[target]:
            val = r["value_used"]
            val_str = f"{val:.4g}" if isinstance(val, (int, float)) else str(val)
            print(f"  #{r['rank']:2}  importance={r['importance']:.4f}  value={val_str:>12}  [{r['source']:12}]  {r['name']}")
    empty = debug_payload.get("empty_feature_names", [])
    if empty:
        print()
        print("--- Leere / fehlende Features (im Modell mit 0 gefüllt, damit es läuft) ---")
        print("  Diese Werte standen in features.json nicht bzw. waren null:")
        for name in empty:
            print(f"    • {name}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict benefit buckets from features.json")
    parser.add_argument("--features", default=None, help="Path to features.json (default: working_data/features.json)")
    parser.add_argument("--output", default=None, help="Path for predictions JSON (default: frontend_data/outputs_for_frontend.json)")
    parser.add_argument("--debug", action="store_true", help="Write prediction_debug.json with feature usage and importance")
    parser.add_argument("--debug-out", default=None, help="Path for debug JSON (default: frontend_data/prediction_debug.json)")
    args = parser.parse_args()

    features_path = Path(args.features) if args.features else WORKING_FEATURES
    output_path = Path(args.output) if args.output else OUTPUT_JSON

    registry_path = MODELS_DIR / "registry.json"
    if not registry_path.exists():
        print(f"Registry not found: {registry_path}")
        print("Train models first: python 2_ml/3_train_models.py")
        sys.exit(1)

    if not features_path.exists():
        print(f"Features not found: {features_path}")
        print("Run first: python 3_prediction/calculate_features.py")
        sys.exit(1)

    with open(registry_path, "r") as f:
        registry = json.load(f)
    feature_columns = get_feature_columns(registry_path)
    if not feature_columns:
        print("Could not read feature order from registry.")
        sys.exit(1)

    features_dict = load_features_json(features_path)
    X_df, row_debug = build_X(features_dict, feature_columns)

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
        pred = model.predict(X_df)
        predictions[target] = float(pred[0])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(predictions, f, indent=2)

    # Always build and print full debug to terminal
    debug_payload = build_debug(registry, feature_columns, row_debug, predictions, MODELS_DIR)
    print_debug_to_terminal(debug_payload)

    print(f"Predictions written to {output_path}")

    if args.debug:
        debug_out = Path(args.debug_out) if args.debug_out else (output_path.parent / "prediction_debug.json")
        debug_out.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_out, "w", encoding="utf-8") as f:
            json.dump(debug_payload, f, indent=2, ensure_ascii=False)
        print(f"Debug JSON written to {debug_out}")


if __name__ == "__main__":
    main()
