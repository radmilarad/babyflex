#!/usr/bin/env python3
"""
Calculate ML features from frontend_data for prediction (same as 2_ml pipeline).
================================================================================

Reads:
- frontend_data/frontend_data.json → direct inputs (list_battery_*, pv_*, static_grid_fees, etc.)
- frontend_data/load_consumption_*_preprocessed.csv → timestamp_utc, grid_load_kwh, consumption_kwh, pv_load_kwh

Computes the same feature set as the ML pipeline (2_ml/config.py):
- Direct: DIRECT_INPUT_NAMES from JSON (missing → NaN).
- Load-profile: column stats/percentiles/custom for consumption_load_kwh, pv_load_kwh (column alias consumption_kwh).
- Cross-column: consumption_pv_pearson, consumption_da_*, etc.
- Ratio: battery_usable_per_sum_pv, battery_usable_per_sum_consumption.

Output: working_data/features.json – same feature names as training, for predict_buckets.py.

Usage (from DB root or 3_prediction):
  python 3_prediction/calculate_features.py
  python 3_prediction/calculate_features.py --input frontend_data/load_consumption_X_preprocessed.csv --inputs frontend_data/frontend_data.json
"""
from pathlib import Path
import argparse
import json
import sys

import pandas as pd
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent
if str(DB_ROOT) not in sys.path:
    sys.path.insert(0, str(DB_ROOT))

import importlib.util
_config_spec = importlib.util.spec_from_file_location("ml_config", DB_ROOT / "2_ml" / "config.py")
ml_config = importlib.util.module_from_spec(_config_spec)
_config_spec.loader.exec_module(ml_config)

_ts_spec = importlib.util.spec_from_file_location(
    "timeseries_aggregations", DB_ROOT / "2_ml" / "extraction" / "timeseries_aggregations.py"
)
ts_aggregations = importlib.util.module_from_spec(_ts_spec)
_ts_spec.loader.exec_module(ts_aggregations)


# Preprocessed CSV: consumption_kwh (preprocess_load_and_pv) or consumption_load_kwh
REQUIRED_BASE = ("timestamp_utc", "grid_load_kwh", "pv_load_kwh")
CONSUMPTION_COL = "consumption_kwh"  # or consumption_load_kwh


def find_preprocessed_csv(dir_path: Path) -> Path | None:
    candidates = sorted(dir_path.glob("load_consumption_*_preprocessed.csv"))
    return candidates[0] if candidates else None


def load_preprocessed(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = list(REQUIRED_BASE) + [CONSUMPTION_COL]
    if CONSUMPTION_COL not in df.columns and "consumption_load_kwh" in df.columns:
        need = list(REQUIRED_BASE) + ["consumption_load_kwh"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"CSV must have {need}. Missing: {missing}. Found: {list(df.columns)}")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    if "consumption_kwh" not in df.columns and "consumption_load_kwh" in df.columns:
        df["consumption_kwh"] = df["consumption_load_kwh"]
    return df


def build_ml_df(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame for extractors: consumption_kwh + pv_load_kwh (same names/aliases as 2_ml)."""
    out = df[["timestamp_utc", "consumption_kwh", "pv_load_kwh"]].copy()
    if "grid_load_kwh" in df.columns:
        out["grid_load_kwh"] = df["grid_load_kwh"]
    return out


def load_direct_inputs(path: Path) -> dict[str, float]:
    with open(path, "r") as f:
        data = json.load(f)
    direct_names = getattr(ml_config, "DIRECT_INPUT_NAMES", [])
    out = {}
    for k in direct_names:
        v = data.get(k)
        if v is None:
            out[k] = np.nan
        elif isinstance(v, (int, float)):
            out[k] = float(v)
        else:
            out[k] = np.nan
    return out


def compute_ratio_features(df: pd.DataFrame, direct: dict) -> dict[str, float]:
    ratio_specs = getattr(ml_config, "RATIO_FEATURES", [])
    out = {}
    den_cols = {"pv_load_kwh": "pv_load_kwh", "consumption_load_kwh": "consumption_kwh"}
    for spec in ratio_specs:
        name = spec.get("name")
        num_key = spec.get("numerator")
        den_col = spec.get("denominator_sum_column")
        if not name or not num_key or not den_col:
            continue
        col = den_cols.get(den_col, den_col)
        if col not in df.columns:
            out[name] = np.nan
            continue
        num_val = direct.get(num_key)
        den_val = df[col].sum()
        if pd.isna(num_val) or den_val is None or den_val == 0:
            out[name] = np.nan
        else:
            out[name] = float(num_val) / float(den_val)
    return out


def nan_to_none(obj: dict) -> dict:
    out = {}
    for k, v in obj.items():
        if isinstance(v, (float, np.floating)) and np.isnan(v):
            out[k] = None
        elif isinstance(v, dict):
            out[k] = nan_to_none(v)
        else:
            out[k] = v
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate ML features from frontend_data → features.json")
    frontend = SCRIPT_DIR / "frontend_data"
    working = SCRIPT_DIR / "working_data"
    default_csv = find_preprocessed_csv(frontend)
    parser.add_argument("--input", default=str(default_csv) if default_csv else None, help="Preprocessed CSV (default: frontend_data/load_consumption_*_preprocessed.csv)")
    parser.add_argument("--output", default=str(working / "features.json"), help="Output path (default: working_data/features.json)")
    parser.add_argument("--inputs", default=str(frontend / "frontend_data.json"), help="Direct inputs JSON (default: frontend_data/frontend_data.json)")
    args = parser.parse_args()

    if not args.input or not Path(args.input).exists():
        raise FileNotFoundError(f"No preprocessed CSV found. Put one in {frontend} or pass --input. Run preprocess_load_and_pv.py first.")
    inputs_path = Path(args.inputs)
    if not inputs_path.exists():
        raise FileNotFoundError(f"Inputs JSON not found: {inputs_path}")

    df_raw = load_preprocessed(Path(args.input))
    df = build_ml_df(df_raw)
    direct = load_direct_inputs(inputs_path)

    specs = getattr(ml_config, "LOAD_PROFILE_COLUMN_SPECS", ml_config.TIMESERIES_COLUMN_SPECS)
    df_names = getattr(ml_config, "LOAD_PROFILE_DF_FEATURE_NAMES", ml_config.TIMESERIES_DF_FEATURE_NAMES)
    column_and_df = ts_aggregations.extract_all_from_config(df, specs, df_names)
    ratio = compute_ratio_features(df, direct)

    all_features = {**direct, **column_and_df, **ratio}

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(nan_to_none(all_features), f, indent=2)

    print(f"Features: {len(all_features)} keys")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
