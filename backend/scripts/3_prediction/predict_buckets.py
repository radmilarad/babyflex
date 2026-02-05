#!/usr/bin/env python3
"""
Hierarchical prediction of benefit buckets.
============================================

Uses hierarchical models where predictions from earlier models become features for later ones:
1. trading_revenue: base_features only
2. energy_procurement_optimization: base_features + pred_trading_revenue
3. peak_shaving_benefit: base_features + pred_trading_revenue + pred_energy_procurement_optimization

Models and feature order from 3_prediction/models/registry.json.
Reads working_data/features.json (from calculate_features.py).
Writes frontend_data/outputs_for_frontend.json.

Usage (from DB root or 3_prediction):
  python 3_prediction/preprocess_load_and_pv.py   # once: preprocess raw data
  python 3_prediction/calculate_features.py       # once: build features from frontend_data
  python 3_prediction/predict_buckets.py          # predict and write outputs_for_frontend.json
  python 3_prediction/predict_buckets.py --debug  # same + write prediction_debug.json
"""
from pathlib import Path
import argparse
import json
import sys

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent

MODELS_DIR = SCRIPT_DIR / "models"
WORKING_FEATURES = SCRIPT_DIR / "working_data" / "features.json"
OUTPUT_JSON = SCRIPT_DIR / "frontend_data" / "outputs_for_frontend.json"
DEBUG_JSON = SCRIPT_DIR / "frontend_data" / "prediction_debug.json"


def load_registry(registry_path: Path) -> dict:
    """Load model registry with feature order and model metadata."""
    with open(registry_path, "r") as f:
        return json.load(f)


def load_features_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def build_feature_vector(
    features_dict: dict,
    base_features: list[str],
    predictions_so_far: dict[str, float],
    target_name: str,
    model_order: list[str],
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Build feature vector for a specific target model.
    
    For hierarchical models:
    - trading_revenue: only base_features
    - energy_procurement_optimization: base_features + pred_trading_revenue
    - peak_shaving_benefit: base_features + pred_trading_revenue + pred_energy_procurement_optimization
    """
    # Start with base features
    feature_columns = list(base_features)
    
    # Add prediction features from earlier models in the hierarchy
    target_idx = model_order.index(target_name)
    for i in range(target_idx):
        prev_target = model_order[i]
        pred_feature_name = f"pred_{prev_target}"
        feature_columns.append(pred_feature_name)
    
    # Build the row
    row = []
    row_debug = []
    
    for col in feature_columns:
        # Check if it's a prediction feature
        if col.startswith("pred_"):
            pred_target = col[5:]  # Remove "pred_" prefix
            v = predictions_so_far.get(pred_target)
            if v is not None:
                row.append(float(v))
                row_debug.append({
                    "name": col,
                    "value": float(v),
                    "source": "predicted",
                    "value_in_features": float(v)
                })
            else:
                row.append(0.0)
                row_debug.append({
                    "name": col,
                    "value": 0.0,
                    "source": "missing_prediction",
                    "value_in_features": None
                })
        else:
            # Regular feature from features.json
            v = features_dict.get(col)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                row.append(0.0)
                row_debug.append({
                    "name": col,
                    "value": 0.0,
                    "source": "imputed",
                    "value_in_features": None
                })
            else:
                try:
                    x = float(v)
                    row.append(x)
                    row_debug.append({
                        "name": col,
                        "value": x,
                        "source": "from_features",
                        "value_in_features": x
                    })
                except (TypeError, ValueError):
                    row.append(0.0)
                    row_debug.append({
                        "name": col,
                        "value": 0.0,
                        "source": "imputed",
                        "value_in_features": None
                    })
    
    arr = np.array([row], dtype=np.float64)
    X_df = pd.DataFrame(arr, columns=feature_columns)
    return X_df, row_debug


def predict_hierarchical(
    features_dict: dict,
    registry: dict,
    models_dir: Path,
) -> tuple[dict[str, float], dict[str, list[dict]]]:
    """
    Make predictions in hierarchical order.
    Returns (predictions, debug_per_target).
    """
    try:
        import joblib
    except ImportError:
        print("joblib required: pip install joblib")
        sys.exit(1)
    
    model_order = registry.get("model_order", [
        "trading_revenue",
        "energy_procurement_optimization",
        "peak_shaving_benefit"
    ])
    base_features = registry.get("base_features", [])
    
    predictions = {}
    debug_per_target = {}
    
    for target in model_order:
        model_path = models_dir / f"{target}_model.joblib"
        if not model_path.exists():
            print(f"Warning: Model not found: {model_path}")
            predictions[target] = None
            continue
        
        # Build feature vector for this target
        X_df, row_debug = build_feature_vector(
            features_dict,
            base_features,
            predictions,  # predictions so far
            target,
            model_order
        )
        
        # Load model and predict
        model = joblib.load(model_path)
        pred = model.predict(X_df)
        predictions[target] = float(pred[0])
        debug_per_target[target] = row_debug
        
        print(f"  {target}: {predictions[target]:,.2f} € (using {len(X_df.columns)} features)")
    
    return predictions, debug_per_target


def build_debug_payload(
    registry: dict,
    predictions: dict,
    debug_per_target: dict[str, list[dict]],
    models_dir: Path,
) -> dict:
    """Build comprehensive debug payload."""
    model_order = registry.get("model_order", [])
    
    # Summary per target
    targets_summary = {}
    for target in model_order:
        if target not in debug_per_target:
            continue
        row_debug = debug_per_target[target]
        n_total = len(row_debug)
        n_from_features = sum(1 for d in row_debug if d["source"] == "from_features")
        n_predicted = sum(1 for d in row_debug if d["source"] == "predicted")
        n_imputed = sum(1 for d in row_debug if d["source"] == "imputed")
        
        targets_summary[target] = {
            "prediction": predictions.get(target),
            "n_features": n_total,
            "n_from_features_json": n_from_features,
            "n_from_predictions": n_predicted,
            "n_imputed": n_imputed,
            "features_used": row_debug,
        }
    
    # Model performance from registry
    results = registry.get("results", {})
    
    return {
        "summary": {
            "model_type": registry.get("model_type", "unknown"),
            "model_order": model_order,
            "training_date": registry.get("training_date"),
            "models_dir": str(models_dir),
        },
        "predictions": predictions,
        "model_performance": {
            target: {
                "cv_r2": results.get(target, {}).get("cv_r2"),
                "test_r2": results.get(target, {}).get("test_r2"),
                "mae": results.get(target, {}).get("mae"),
            }
            for target in model_order
        },
        "targets_detail": targets_summary,
    }


def print_summary(predictions: dict, registry: dict) -> None:
    """Print prediction summary to terminal."""
    print("\n" + "=" * 60)
    print("HIERARCHICAL PREDICTIONS")
    print("=" * 60)
    
    results = registry.get("results", {})
    model_order = registry.get("model_order", [])
    
    print(f"\n{'Target':<45} {'Prediction':>15} {'MAE (Train)':>12}")
    print("-" * 72)
    
    total = 0
    for target in model_order:
        pred = predictions.get(target)
        mae = results.get(target, {}).get("mae", 0)
        if pred is not None:
            print(f"{target:<45} {pred:>15,.2f} € {mae:>10,.0f} €")
            total += pred
        else:
            print(f"{target:<45} {'N/A':>15} {mae:>10,.0f} €")
    
    print("-" * 72)
    print(f"{'TOTAL BENEFIT':<45} {total:>15,.2f} €")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hierarchical prediction of benefit buckets")
    parser.add_argument("--features", default=None, help="Path to features.json")
    parser.add_argument("--output", default=None, help="Path for predictions JSON")
    parser.add_argument("--debug", action="store_true", help="Write prediction_debug.json")
    parser.add_argument("--debug-out", default=None, help="Path for debug JSON")
    args = parser.parse_args()
    
    features_path = Path(args.features) if args.features else WORKING_FEATURES
    output_path = Path(args.output) if args.output else OUTPUT_JSON
    
    registry_path = MODELS_DIR / "registry.json"
    if not registry_path.exists():
        print(f"Registry not found: {registry_path}")
        print("Train models first or copy them to 3_prediction/models/")
        sys.exit(1)
    
    if not features_path.exists():
        print(f"Features not found: {features_path}")
        print("Run first: python 3_prediction/calculate_features.py")
        sys.exit(1)
    
    registry = load_registry(registry_path)
    features_dict = load_features_json(features_path)
    
    print("\nPredicting in hierarchical order...")
    predictions, debug_per_target = predict_hierarchical(features_dict, registry, MODELS_DIR)
    
    # Write predictions
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(predictions, f, indent=2)
    
    print_summary(predictions, registry)
    print(f"Predictions written to {output_path}")
    
    # Write debug if requested
    if args.debug:
        debug_payload = build_debug_payload(registry, predictions, debug_per_target, MODELS_DIR)
        debug_out = Path(args.debug_out) if args.debug_out else DEBUG_JSON
        debug_out.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_out, "w", encoding="utf-8") as f:
            json.dump(debug_payload, f, indent=2, ensure_ascii=False)
        print(f"Debug JSON written to {debug_out}")


if __name__ == "__main__":
    main()
