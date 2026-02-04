#!/usr/bin/env python3
"""
Show feature importances (GradientBoosting) or coefficients (Ridge) for all trained models.
=========================================================================================

Reads registry.json and optionally the .joblib models from 3_prediction/models/
(or 2_ml/artifacts/models/ if registry is only there).
Prints per-target: feature name and importance/coefficient, sorted by absolute value descending.

Usage (from DB root or 3_prediction):
  python 3_prediction/show_model_coefficients.py
"""
from pathlib import Path
import json
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent

# Prefer 3_prediction/models, fallback to 2_ml/artifacts/models
MODELS_3P = SCRIPT_DIR / "models"
MODELS_2ML = DB_ROOT / "2_ml" / "artifacts" / "models"


def find_registry() -> Path:
    for d in (MODELS_3P, MODELS_2ML):
        r = d / "registry.json"
        if r.exists():
            return r
    return MODELS_2ML / "registry.json"


def main() -> None:
    registry_path = find_registry()
    if not registry_path.exists():
        print(f"Registry not found: {registry_path}")
        print("Train models first: python 2_ml/3_train_models.py")
        sys.exit(1)

    with open(registry_path, "r") as f:
        registry = json.load(f)

    models_dir = registry_path.parent
    print(f"Registry: {registry_path}")
    print(f"Models dir: {models_dir}\n")

    for target_name, meta in registry.items():
        if not isinstance(meta, dict):
            continue
        imp = meta.get("feature_importance")
        model_type = meta.get("model_type", "?")
        if not imp:
            print(f"--- {target_name} ({model_type}) --- no feature_importance in registry\n")
            continue
        # Sort by absolute value descending
        items = [(k, float(v)) for k, v in imp.items()]
        items.sort(key=lambda x: abs(x[1]), reverse=True)
        print(f"--- {target_name} ({model_type}) ---")
        print(f"    (Feature importance sums to 1.0 for tree models; Ridge: absolute coefficients)")
        for name, val in items:
            print(f"    {val:12.6f}  {name}")
        print()

    # Optionally show live from .joblib (same order as registry)
    try:
        import joblib
    except ImportError:
        return
    print("--- From loaded .joblib models (same values as registry) ---")
    for target_name in ("peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"):
        path = models_dir / f"{target_name}_model.joblib"
        if not path.exists():
            print(f"  {target_name}: model file not found")
            continue
        model = joblib.load(path)
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            names = list(registry.get(target_name, {}).get("feature_importance", {}).keys())
            if len(names) == len(imp):
                top = sorted(zip(names, imp), key=lambda x: abs(x[1]), reverse=True)[:10]
                print(f"  {target_name} (top 10): {[(n, round(v, 6)) for n, v in top]}")
            else:
                print(f"  {target_name}: feature_importances_ length {len(imp)}")
        elif hasattr(model, "coef_"):
            coef = model.coef_
            names = list(registry.get(target_name, {}).get("feature_importance", {}).keys())
            if len(names) == len(coef):
                top = sorted(zip(names, coef), key=lambda x: abs(x[1]), reverse=True)[:10]
                print(f"  {target_name} (Ridge, top 10): {[(n, round(v, 6)) for n, v in top]}")
            else:
                print(f"  {target_name}: coef_ length {len(coef)}")
        else:
            print(f"  {target_name}: no feature_importances_ or coef_")
    print()


if __name__ == "__main__":
    main()
