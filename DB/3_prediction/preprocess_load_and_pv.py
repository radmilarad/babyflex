#!/usr/bin/env python3
"""
Preprocessing: Load + PV → grid_load_kwh, consumption_kwh
==========================================================

1. Load consumption data from Excel or CSV (auto-detect). Required columns only:
   "timestamp" and "value kwh".

2. Simulate PV profile using pvlib (from 1a_simulate_pv_profile.ipynb), driven by
   pv_peak_power from exemplary_data/frontend_inputs.json (annual target in MWh).
   Uses fixed location (no Google API); case_name and address are not used.

3. Merge load + PV with pv_consumed_percentage (Eigenverbrauchsanteil, 0..1) and
   weekday scaling (as in "Add the PV Data" in 2_preprocessing_consumption.ipynb):
   scale PV self-consumption per weekday to match grid-load weekday shares; then:
   - grid_load_kwh: original load from grid (kWh per 15-min)
   - consumption_kwh: grid_load_kwh + scaled PV (kWh per 15-min)

Output: CSV with columns timestamp_utc, grid_load_kwh, consumption_kwh.

Usage (from project root or 3_prediction):
  python 3_prediction/preprocess_load_and_pv.py --load exemplary_data/2024_timeseries_OsmoHolz.xlsx
  python 3_prediction/preprocess_load_and_pv.py --load path/to/timeseries.csv --inputs exemplary_data/frontend_inputs.json
"""
from pathlib import Path
import argparse
import json
import pandas as pd
import numpy as np


# -----------------------------------------------------------------------------
# (1) Load consumption data (Excel or CSV)
# -----------------------------------------------------------------------------

REQUIRED_LOAD_COLUMNS = ("timestamp", "value kwh")


def load_consumption_data(path: str) -> pd.DataFrame:
    """
    Load load/consumption timeseries from Excel or CSV.
    Only accepts columns: "timestamp" and "value kwh".
    Returns DataFrame with columns: timestamp_utc, grid_load_kwh.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Load file not found: {path}")

    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=0)
    else:
        df = pd.read_csv(path, parse_dates=False)

    missing = [c for c in REQUIRED_LOAD_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Load file must have exactly these columns: {REQUIRED_LOAD_COLUMNS}. "
            f"Missing: {missing}. Found: {list(df.columns)}"
        )

    df = df[list(REQUIRED_LOAD_COLUMNS)].copy()
    df["value kwh"] = pd.to_numeric(df["value kwh"], errors="coerce")
    df["value kwh"] = df["value kwh"].clip(lower=0)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.rename(columns={"value kwh": "grid_load_kwh"})[["timestamp_utc", "grid_load_kwh"]]
    return df


# -----------------------------------------------------------------------------
# (2) Simulate PV profile (from 1a_simulate_pv_profile.ipynb, no plots, fixed location)
# -----------------------------------------------------------------------------

def simulate_pv_profile(pv_peak_power_mwh: float, year: int = 2024) -> pd.DataFrame:
    """
    Simulate PV generation (15-min resolution) using pvlib.
    pv_peak_power_mwh: target annual energy in MWh (scaling factor in notebook).
    Uses fixed location (Central Germany); no Google API.
    Returns DataFrame with columns: timestamp_utc, value (kWh per interval).
    """
    from pvlib import location as pvlib_location
    from pvlib import modelchain
    from pvlib.pvsystem import Array, FixedMount, PVSystem
    from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

    # Fixed location (Central Germany) – no address/API
    lat, lon, altitude = 51.0, 10.0, 200.0
    site = pvlib_location.Location(lat, lon, "UTC", altitude, "Central Germany")

    start_time = pd.Timestamp(f"{year}-01-01 00:00:00", tz=site.tz)
    end_time = pd.Timestamp(f"{year}-12-31 23:45:00", tz=site.tz)
    times = pd.date_range(start=start_time, end=end_time, freq="15min")

    clearsky = site.get_clearsky(times)

    module_parameters = {"pdc0": 250, "gamma_pdc": -0.004, "b": 0.05}
    inverter_parameters = {"pdc0": 25000, "eta_inv_nom": 0.96}
    temperature_model_parameters = TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]

    array_configs = [
        {"surface_tilt": 15, "surface_azimuth": 90},
        {"surface_tilt": 15, "surface_azimuth": 270},
    ]
    num_modules = 100
    modules_per_string = 20
    strings_per_inverter = num_modules // modules_per_string

    arrays = []
    for config in array_configs:
        mount = FixedMount(surface_tilt=config["surface_tilt"], surface_azimuth=config["surface_azimuth"])
        array = Array(
            mount=mount,
            module_parameters=module_parameters,
            temperature_model_parameters=temperature_model_parameters,
            modules_per_string=modules_per_string,
            strings=strings_per_inverter,
        )
        arrays.append(array)

    system = PVSystem(arrays=arrays, inverter_parameters=inverter_parameters)
    mc = modelchain.ModelChain(system, site, aoi_model="ashrae", spectral_model="no_loss")
    mc.run_model(clearsky)

    ac_power = mc.results.ac
    annual_energy_wh = ac_power.sum() / 4
    scaling_factor = pv_peak_power_mwh * 1e6 / annual_energy_wh
    scaled_ac = ac_power * scaling_factor

    result_df = pd.DataFrame({
        "timestamp_utc": times,
        "pv_generation_kwh": scaled_ac.values / (4 * 1e3),
    })
    return result_df


# -----------------------------------------------------------------------------
# (3) Merge load + PV → grid_load_kwh, consumption_kwh (with weekday scaling)
# -----------------------------------------------------------------------------

def merge_load_and_pv(
    df_load: pd.DataFrame,
    df_pv: pd.DataFrame,
    pv_consumed_percentage: float = 1.0,
) -> pd.DataFrame:
    """
    Align load and PV on timestamp_utc. pv_consumed_percentage (0..1) is the share of
    PV generation that counts as self-consumption (Eigenverbrauchsanteil). Apply
    weekday scaling to that PV so the distribution matches grid-load weekday shares
    (same logic as "Add the PV Data" in 2_preprocessing_consumption.ipynb).
    Then: consumption_kwh = grid_load_kwh + pv_scaled.
    """
    df_load = df_load.copy()
    df_pv = df_pv.copy()
    if df_pv["timestamp_utc"].dt.tz is None:
        df_pv["timestamp_utc"] = pd.to_datetime(df_pv["timestamp_utc"], utc=True)
    df_load["timestamp_utc"] = pd.to_datetime(df_load["timestamp_utc"], utc=True)

    # PV self-consumption = generation * pv_consumed_percentage (like own_consumption_ratio in notebook)
    df_pv["pv_self_consumption_kwh"] = df_pv["pv_generation_kwh"] * pv_consumed_percentage

    # Weekday: 0=Monday, 6=Sunday (same as notebook)
    df_load["weekday"] = df_load["timestamp_utc"].dt.dayofweek
    df_pv["weekday"] = df_pv["timestamp_utc"].dt.dayofweek

    # Grid consumption distribution by weekday (share per weekday); ensure all 7 days
    weekday_consumption = df_load.groupby("weekday")["grid_load_kwh"].sum()
    weekday_consumption_share = (weekday_consumption / weekday_consumption.sum()).reindex(range(7), fill_value=0)

    # PV self-consumption per weekday (for weekday scaling)
    pv_by_weekday = df_pv.groupby("weekday")["pv_self_consumption_kwh"].sum()
    total_pv = df_pv["pv_self_consumption_kwh"].sum()
    target_pv_by_weekday = total_pv * weekday_consumption_share

    # Scaling factor per weekday: scale PV so weekday totals match grid distribution
    weekday_scaling_factors = {}
    for wd in range(7):
        pv_wd = pv_by_weekday.get(wd, 0.0)
        target_wd = target_pv_by_weekday[wd]
        if pv_wd > 0:
            weekday_scaling_factors[wd] = target_wd / pv_wd
        else:
            weekday_scaling_factors[wd] = 0.0

    # Apply scaling to self-consumption (preserves intraday pattern within each weekday)
    df_pv["pv_scaled_kwh"] = df_pv.apply(
        lambda row: row["pv_self_consumption_kwh"] * weekday_scaling_factors[row["weekday"]],
        axis=1,
    )

    merged = df_load.merge(
        df_pv[["timestamp_utc", "pv_scaled_kwh"]],
        on="timestamp_utc",
        how="left",
    )
    merged["pv_scaled_kwh"] = merged["pv_scaled_kwh"].fillna(0)
    merged["consumption_kwh"] = merged["grid_load_kwh"] + merged["pv_scaled_kwh"]
    return merged[["timestamp_utc", "grid_load_kwh", "consumption_kwh"]]


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Preprocess load + PV → grid_load_kwh, consumption_kwh")
    parser.add_argument("--load", required=True, help="Path to load timeseries (Excel or CSV)")
    parser.add_argument("--inputs", default=None, help="Path to frontend_inputs.json (default: exemplary_data/frontend_inputs.json)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: same dir as load, suffix _preprocessed.csv)")
    parser.add_argument("--year", type=int, default=2024, help="Year for PV simulation (default: 2024)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    if args.inputs is None:
        args.inputs = script_dir / "exemplary_data" / "frontend_inputs.json"
    else:
        args.inputs = Path(args.inputs)
    if not args.inputs.exists():
        raise FileNotFoundError(f"Inputs JSON not found: {args.inputs}")

    with open(args.inputs, "r") as f:
        inputs = json.load(f)
    # pv_peak_power in MWh (annual target); fallback to pv_annual_total (interpret as MWh or kWh)
    pv_peak_power_mwh = inputs.get("pv_peak_power")
    if pv_peak_power_mwh is None:
        pv_annual = inputs.get("pv_annual_total", 50)
        pv_peak_power_mwh = pv_annual if pv_annual > 10 else pv_annual / 1000.0  # assume kWh if < 10
    pv_peak_power_mwh = float(pv_peak_power_mwh)

    # pv_consumed_percentage: 0..1 (or 0..100 if value > 1)
    pv_consumed = inputs.get("pv_consumed_percentage", 1.0)
    pv_consumed = float(pv_consumed)
    if pv_consumed > 1.0:
        pv_consumed = pv_consumed / 100.0
    pv_consumed = max(0.0, min(1.0, pv_consumed))

    # (1) Load consumption data
    load_path = Path(args.load)
    if not load_path.is_absolute():
        if (Path.cwd() / load_path).exists():
            load_path = (Path.cwd() / load_path).resolve()
        else:
            load_path = (script_dir / load_path).resolve()
    df_load = load_consumption_data(str(load_path))
    print(f"Load data: {len(df_load)} rows, {df_load['grid_load_kwh'].sum():,.2f} kWh total")
    print(f"pv_consumed_percentage: {pv_consumed:.2%}")

    # (2) Simulate PV
    df_pv = simulate_pv_profile(pv_peak_power_mwh, year=args.year)
    print(f"PV simulation: {pv_peak_power_mwh} MWh/year target, {df_pv['pv_generation_kwh'].sum():,.2f} kWh total")

    # (3) Merge and compute consumption (with pv_consumed_percentage)
    df_out = merge_load_and_pv(df_load, df_pv, pv_consumed_percentage=pv_consumed)
    print(f"Consumption (grid + PV): {df_out['consumption_kwh'].sum():,.2f} kWh total")

    # Output
    if args.output is None:
        args.output = load_path.parent / (load_path.stem + "_preprocessed.csv")
    else:
        args.output = Path(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(args.output, index=False)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
