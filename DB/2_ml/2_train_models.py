#!/usr/bin/env python3
"""
Step 2: Training – Modelle fitten
==================================

Trainiert alle drei Benefit-Modelle (peak_shaving, energy_procurement, trading_revenue),
speichert unter 2_ml/artifacts/models/.

Aus Projektroot:  python 2_ml/2_train_models.py
"""
import sys
import argparse
from pathlib import Path
from importlib import import_module

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_train = import_module("2_ml.training.train_models")
_compare = import_module("2_ml.training.compare_models")
train_all_models = _train.train_all_models
print_model_overview = _compare.print_model_overview


def main():
    parser = argparse.ArgumentParser(description="Step 2: Train battery benefit models")
    parser.add_argument(
        "--model",
        choices=["auto", "xgboost", "gradient_boosting", "ridge"],
        default="auto",
        help="Model type to use",
    )
    parser.add_argument(
        "--no-group-split",
        action="store_true",
        help="Disable group-aware train/test split",
    )
    parser.add_argument("--quiet", action="store_true", help="Less output")
    args = parser.parse_args()

    train_all_models(
        model_type=args.model,
        group_aware=not args.no_group_split,
        verbose=not args.quiet,
    )
    print_model_overview()
    print("\n✅ Step 2 done. Modelle → 2_ml/artifacts/models/")


if __name__ == "__main__":
    main()
