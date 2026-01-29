#!/usr/bin/env python3
"""
Step 3a: Evaluation – Metriken (R², MAE, RMSE, CV) + optional SHAP
==================================================================

Bewertet die trainierten Modelle auf den Features, optional SHAP-Analyse.

Aus Projektroot:  python 2_ml/3_evaluate_models.py
"""
import sys
import argparse
from pathlib import Path
from importlib import import_module

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_eval = import_module("2_ml.training.evaluate_models")
_reg = import_module("2_ml.training.model_registry")
evaluate_models = _eval.evaluate_models
explain_model = _eval.explain_model
compare_feature_effects = _eval.compare_feature_effects
ModelRegistry = _reg.ModelRegistry


def main():
    parser = argparse.ArgumentParser(description="Step 3a: Evaluate battery benefit models")
    parser.add_argument("--shap", action="store_true", help="Run SHAP analysis")
    parser.add_argument(
        "--target",
        choices=["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue", "all"],
        default="all",
        help="Target model(s) to analyze",
    )
    parser.add_argument("--save-plots", action="store_true", help="Save SHAP plots to 2_ml/artifacts/shap/")
    args = parser.parse_args()

    results = evaluate_models(verbose=True)
    if not results.empty:
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        print(results.to_string(index=False))

    if args.shap:
        registry = ModelRegistry()
        targets = list(registry.models.keys()) if args.target == "all" else [args.target]
        for target in targets:
            if target in registry.models:
                try:
                    explain_model(target, registry=registry, save_plots=args.save_plots, verbose=True)
                except Exception as e:
                    print(f"\nSHAP analysis failed for {target}: {e}")
        print("\n" + "=" * 60)
        print("FEATURE IMPORTANCE ACROSS ALL MODELS")
        print("=" * 60)
        try:
            comparison = compare_feature_effects(registry)
            if not comparison.empty:
                print(comparison.to_string())
        except Exception as e:
            print(f"Could not compare features: {e}")

    print("\n✅ Step 3a done.")


if __name__ == "__main__":
    main()
