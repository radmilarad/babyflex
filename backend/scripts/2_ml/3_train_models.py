#!/usr/bin/env python3
"""
Step 3: Training – Modelle fitten (Standard-Benefits + optional Sondermodell)
=============================================================================

Trainiert Benefit-Modelle (1=peak_shaving, 2=energy_procurement, 3=trading_revenue,
4=Sondermodell peak_shaving nur für usage_hours > Threshold). Features aus
artifacts/features/<target>/selected_feature_list.txt falls vorhanden.
Sondermodell (4) → 2_ml/artifacts/models_peak_usage/.

  python 2_ml/3_train_models.py
  python 2_ml/3_train_models.py --target 4
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
TARGETS = _train.TARGETS
print_model_overview = _compare.print_model_overview

# Default aus config_models
_config = import_module("2_ml.config_models")
DEFAULT_MODEL = getattr(_config, "DEFAULT_MODEL_TYPE", "auto")
PEAK_USAGE_KEY = getattr(_config, "TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS", "target_peak_shaving_benefit_peak_usage_hours")

# Gleiche Reihenfolge wie in 2_feature_selection.py: 1–4 = ein Target, 5 = alle
ALL_TARGET_KEYS = TARGETS + [PEAK_USAGE_KEY]
TARGET_CHOICE_TO_KEY = {
    "1": TARGETS[0],           # target_peak_shaving_benefit
    "2": TARGETS[1],           # target_energy_procurement_optimization
    "3": TARGETS[2],           # target_trading_revenue
    "4": PEAK_USAGE_KEY,       # target_peak_shaving_benefit_peak_usage_hours
    "5": None,                 # None = alle
}
TARGET_CHOICES_CLI = ["1", "2", "3", "4", "peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue", "peak_shaving_benefit_peak_usage_hours"]
TARGET_TO_COL = {
    "1": TARGETS[0],
    "2": TARGETS[1],
    "3": TARGETS[2],
    "4": PEAK_USAGE_KEY,
    "peak_shaving_benefit": TARGETS[0],
    "energy_procurement_optimization": TARGETS[1],
    "trading_revenue": TARGETS[2],
    "peak_shaving_benefit_peak_usage_hours": PEAK_USAGE_KEY,
}


def _prompt_target_choice():
    """Fragt nach 1–5 (gleiche Reihenfolge wie 2_feature_selection.py), gibt Liste der Target-Keys zurück."""
    prompt = (
        "Target? 1=peak_shaving_benefit, 2=energy_procurement_optimization, "
        "3=trading_revenue, 4=peak_shaving_benefit_peak_usage_hours, 5=alle: "
    )
    while True:
        try:
            choice = input(prompt).strip()
        except EOFError:
            print("Keine Eingabe (z. B. --target verwenden).")
            return None
        if choice in TARGET_CHOICE_TO_KEY:
            if TARGET_CHOICE_TO_KEY[choice] is None:
                return list(ALL_TARGET_KEYS)
            return [TARGET_CHOICE_TO_KEY[choice]]
        print("Ungültig. Bitte 1, 2, 3, 4 oder 5 eingeben.")


def main():
    parser = argparse.ArgumentParser(
        description="Step 3: Train battery benefit models. Features aus artifacts/features/<target>/selected_feature_list.txt falls vorhanden."
    )
    parser.add_argument(
        "--model",
        choices=["auto", "xgboost", "gradient_boosting", "ridge"],
        default=DEFAULT_MODEL,
        help="Model type (default from config: DEFAULT_MODEL_TYPE)",
    )
    parser.add_argument(
        "--target",
        choices=TARGET_CHOICES_CLI,
        default=None,
        help="Nur dieses Modell (1–4 oder Kurzname). Ohne --target: interaktive Auswahl (1–5, 5=alle).",
    )
    parser.add_argument(
        "--no-group-split",
        action="store_true",
        help="Disable group-aware train/test split",
    )
    parser.add_argument("--quiet", action="store_true", help="Less output")
    parser.add_argument(
        "--test-clients",
        type=str,
        default=None,
        help="Comma-separated client names for test set (rest = train). Overrides random group split.",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=42,
        help="Random seed for train/test group split (default: 42)",
    )
    args = parser.parse_args()

    test_clients_list = None
    if args.test_clients:
        test_clients_list = [s.strip() for s in args.test_clients.split(",") if s.strip()]

    if args.target:
        targets_filter = [TARGET_TO_COL[args.target]]
    else:
        targets_filter = _prompt_target_choice()
        if targets_filter is None:
            return

    registry, peak_usage_registry = train_all_models(
        model_type=args.model,
        group_aware=not args.no_group_split,
        verbose=not args.quiet,
        test_clients=test_clients_list,
        split_seed=args.split_seed,
        targets_filter=targets_filter,
    )
    # Nur die in diesem Lauf trainierten Targets anzeigen
    only_main = [t.replace("target_", "", 1) for t in targets_filter if t != PEAK_USAGE_KEY]
    if only_main:
        print_model_overview(registry, only_targets=only_main)
    if PEAK_USAGE_KEY in targets_filter and peak_usage_registry is not None:
        print_model_overview(peak_usage_registry, only_targets=["peak_shaving_benefit"])
    has_peak_usage = PEAK_USAGE_KEY in targets_filter
    out_msg = "2_ml/artifacts/models/" + (" (+ 2_ml/artifacts/models_peak_usage/)" if has_peak_usage else "")
    print("\n✅ Step 3 done. Modelle → " + out_msg)


if __name__ == "__main__":
    main()
