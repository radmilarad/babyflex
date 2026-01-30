#!/usr/bin/env python3
"""
Calculate ML features from preprocessed load/PV CSV for prediction.
==================================================================

Reads preprocessed CSV from output_to_ui (e.g. load_consumption_*_preprocessed.csv)
with columns: timestamp_utc, grid_load_kwh, consumption_kwh, pv_load_kwh.

Computes the same feature set as the ML pipeline (2_ml/config.py):
- Direct inputs from frontend_inputs.json (unchanged: battery params, pv_annual_total, etc.).
- Column-based: stats, percentiles, custom aggregations for grid_load_kwh, consumption_kwh.
- Cross-column: self_consumption_ratio, load_pv_correlation, temporal ratios.

Output: working_data/features.json – same feature names as training, so you can
apply the trained model coefficients for estimation (e.g. KPI prediction).

Usage (from DB root or 3_prediction):
  python 3_prediction/calculate_features.py
  python 3_prediction/calculate_features.py --input output_to_ui/load_consumption_AmazonenWerkeDreyer_preprocessed.csv --output working_data/features.json
"""
from pathlib import Path
import argparse
import json
import sys

import pandas as pd
import numpy as np

# Project root = DB (parent of 3_prediction)
SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent
if str(DB_ROOT) not in sys.path:
    sys.path.insert(0, str(DB_ROOT))

# ML config and extraction logic (same as training)
import importlib.util
_config_spec = importlib.util.spec_from_file_location(
    "ml_config", DB_ROOT / "2_ml" / "config.py"
)
ml_config = importlib.util.module_from_spec(_config_spec)
_config_spec.loader.exec_module(ml_config)

_ts_spec = importlib.util.spec_from_file_location(
    "timeseries_aggregations", DB_ROOT / "2_ml" / "extraction" / "timeseries_aggregations.py"
)
ts_aggregations = importlib.util.module_from_spec(_ts_spec)
_ts_spec.loader.exec_module(ts_aggregations)


# -----------------------------------------------------------------------------
# Load preprocessed CSV
# -----------------------------------------------------------------------------

REQUIRED_COLUMNS = ("timestamp_utc", "grid_load_kwh", "consumption_load_kwh", "pv_load_kwh")


def find_preprocessed_csv(output_dir: Path) -> Path | None:
    """First load_consumption_*_preprocessed.csv in output_to_ui."""
    if not output_dir.exists():
        return None
    candidates = sorted(output_dir.glob("load_consumption_*_preprocessed.csv"))
    return candidates[0] if candidates else None


def load_preprocessed(path: Path) -> pd.DataFrame:
    """Load preprocessed CSV; ensure required columns."""
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Preprocessed CSV must have columns: {REQUIRED_COLUMNS}. Missing: {missing}. Found: {list(df.columns)}"
        )
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df


def build_ml_input_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build DataFrame in the shape expected by ML extractors.
    - timestamp, load_kwh, generation_kwh, grid_export_kwh for cross-features.
    - grid_load_kwh, consumption_kwh for column specs (already present).
    """
    out = df[list(REQUIRED_COLUMNS)].copy()
    out["timestamp"] = out["timestamp_utc"]
    # load_kwh = total consumption (used by temporal + load_pv_correlation)
    out["load_kwh"] = out["consumption_kwh"].copy()
    # generation_kwh: PV part consumed (proxy; we don't have total PV generation)
    out["generation_kwh"] = out["pv_load_kwh"].copy()
    # grid_export_kwh: not in preprocessed data – placeholder 0 (self_consumption_ratio = 1 - 0/gen = 1.0)
    out["grid_export_kwh"] = 0.0
    return out


# -----------------------------------------------------------------------------
# Feature calculation (same names as 2_ml pipeline)
# -----------------------------------------------------------------------------

def calculate_column_features(df: pd.DataFrame) -> dict[str, float]:
    """Column-based features from LOAD_PROFILE_COLUMN_SPECS (grid_load_kwh, consumption_kwh)."""
    features: dict[str, float] = {}
    specs = getattr(ml_config, "LOAD_PROFILE_COLUMN_SPECS", ml_config.TIMESERIES_COLUMN_SPECS)
    for column, spec in specs.items():
        if column not in df.columns:
            continue
        feats = ts_aggregations.extract_column_features(df, column, spec)
        features.update(feats)
    return features


def calculate_cross_features(df: pd.DataFrame) -> dict[str, float]:
    """Cross-column features (self_consumption_ratio, load_pv_correlation, temporal ratios)."""
    features: dict[str, float] = {}
    names = getattr(ml_config, "LOAD_PROFILE_DF_FEATURE_NAMES", ml_config.TIMESERIES_DF_FEATURE_NAMES)
    for name in names:
        if name not in ts_aggregations.CUSTOM_DF_FEATURES:
            features[name] = np.nan
            continue
        try:
            features[name] = float(ts_aggregations.CUSTOM_DF_FEATURES[name](df))
        except Exception:
            features[name] = np.nan
    return features


def load_direct_inputs(path: Path) -> dict[str, float]:
    """Load direct inputs from frontend_inputs.json; values unchanged, numeric for model."""
    with open(path, "r") as f:
        data = json.load(f)
    out = {}
    for k, v in data.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def nan_to_none(obj: dict) -> dict:
    """Replace NaN with None for JSON."""
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
    parser = argparse.ArgumentParser(
        description="Calculate ML features from preprocessed load/PV CSV → features.json"
    )
    input_dir = SCRIPT_DIR / "output_to_ui"
    working_dir = SCRIPT_DIR / "working_data"
    default_input = find_preprocessed_csv(input_dir)
    parser.add_argument(
        "--input",
        default=str(default_input) if default_input else None,
        help="Preprocessed CSV path (default: first load_consumption_*_preprocessed.csv in output_to_ui)",
    )
    parser.add_argument(
        "--output",
        default=str(working_dir / "features.json"),
        help="Output features.json path (default: working_data/features.json)",
    )
    default_inputs = SCRIPT_DIR / "exemplary_data" / "frontend_inputs.json"
    parser.add_argument(
        "--inputs",
        default=str(default_inputs),
        help="Direct inputs JSON (default: exemplary_data/frontend_inputs.json)",
    )
    args = parser.parse_args()

    if not args.input or not Path(args.input).exists():
        raise FileNotFoundError(
            f"No preprocessed CSV found. Put one in {input_dir} or pass --input. "
            "Run preprocess_load_and_pv.py first."
        )

    path = Path(args.input)
    inputs_path = Path(args.inputs)
    if not inputs_path.exists():
        raise FileNotFoundError(f"Inputs JSON not found: {inputs_path}")

    df_raw = load_preprocessed(path)
    df = build_ml_input_df(df_raw)

    # Direct inputs from frontend_inputs.json (unchanged)
    direct_inputs = load_direct_inputs(inputs_path)
    # Same feature set as ML training pipeline (load-profile derived)
    column_features = calculate_column_features(df)
    cross_features = calculate_cross_features(df)
    all_features = {**direct_inputs, **column_features, **cross_features}

    # Optional: add pv_load_kwh–based features (placeholder for later)
    # pv_features = {"pv_load_sum": float(df["pv_load_kwh"].sum()), ...}
    # all_features.update(pv_features)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(nan_to_none(all_features), f, indent=2)

    print(f"Features: {len(all_features)} keys")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
