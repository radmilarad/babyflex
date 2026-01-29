"""
Timeseries-Feature-Logik – ausschließlich Code
==============================================

Alle Berechnungen für Zeitreihen-Features leben hier.
Config (2_ml/config.py) enthält nur die Eingaben:
- welche Spalten, welche stats/percentiles/custom-Namen.

Dieses Modul liefert die Implementierung pro Namen und die
Funktionen extract_all_from_config / list_all_features.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Callable


# -----------------------------------------------------------------------------
# Standard-Statistiken (Name -> Funktion auf pd.Series)
# -----------------------------------------------------------------------------

STAT_FUNCTIONS: Dict[str, Callable[[pd.Series], float]] = {
    "mean": lambda s: s.mean(),
    "std": lambda s: s.std(),
    "min": lambda s: s.min(),
    "max": lambda s: s.max(),
    "sum": lambda s: s.sum(),
    "median": lambda s: s.median(),
    "var": lambda s: s.var(),
    "skew": lambda s: s.skew(),
    "kurtosis": lambda s: s.kurtosis(),
}


# -----------------------------------------------------------------------------
# Custom-Aggregationen pro Spalte (Name -> Funktion auf pd.Series)
# Config verweist per Namen, z.B. "peak_to_mean", "cv"
# -----------------------------------------------------------------------------

CUSTOM_COLUMN_AGGREGATIONS: Dict[str, Callable[[pd.Series], float]] = {
    "peak_to_mean": lambda s: s.max() / s.mean() if s.mean() > 0 else 0,
    "cv": lambda s: s.std() / s.mean() if s.mean() > 0 else 0,
    "iqr": lambda s: np.percentile(s, 75) - np.percentile(s, 25),
    "skewness": lambda s: s.skew() if len(s) > 0 else 0,
    "time_below_20pct": lambda s: (s < 20).mean(),
    "time_above_80pct": lambda s: (s > 80).mean(),
    "cycles_equivalent": lambda s: s.diff().abs().sum() / 200,
    "range": lambda s: s.max() - s.min(),
    "charge_energy": lambda s: s[s > 0].sum() if (s > 0).any() else 0,
    "discharge_energy": lambda s: s[s < 0].abs().sum() if (s < 0).any() else 0,
    "reversals": lambda s: (s.diff().abs() > 0.1).sum(),
    "utilization": lambda s: (s.abs() > 0.01).mean(),
    "peak_to_average": lambda s: s.max() / s.mean() if s.mean() > 0 else 0,
    "export_ratio": lambda s: (s > 0).mean(),
    "capacity_factor": lambda s: s.mean() / s.max() if s.max() > 0 else 0,
    "zero_generation_ratio": lambda s: (s == 0).mean(),
    "price_spread": lambda s: s.max() - s.min(),
    "price_volatility": lambda s: s.std() / s.mean() if s.mean() > 0 else 0,
}


# -----------------------------------------------------------------------------
# Cross-Column-Features (Name -> Funktion auf pd.DataFrame)
# Config listet Namen in TIMESERIES_DF_FEATURE_NAMES
# -----------------------------------------------------------------------------

def _calc_self_consumption(df: pd.DataFrame) -> float:
    if "generation_kwh" not in df.columns or "grid_export_kwh" not in df.columns:
        return np.nan
    gen_sum = df["generation_kwh"].sum()
    export_sum = df["grid_export_kwh"].sum()
    return (1 - (export_sum / gen_sum)) if gen_sum > 0 else np.nan


def _calc_load_pv_corr(df: pd.DataFrame) -> float:
    if "load_kwh" not in df.columns or "generation_kwh" not in df.columns:
        return np.nan
    load = df["load_kwh"].dropna()
    gen = df["generation_kwh"].dropna()
    if len(load) > 10 and len(gen) > 10:
        common = load.index.intersection(gen.index)
        if len(common) > 10:
            return load.loc[common].corr(gen.loc[common])
    return np.nan


def _calc_peak_load_ratio(df: pd.DataFrame) -> float:
    if "timestamp" not in df.columns or "load_kwh" not in df.columns:
        return np.nan
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    peak_mask = df["hour"].between(9, 17)
    load = df["load_kwh"]
    if peak_mask.any() and (~peak_mask).any():
        return load[peak_mask].sum() / load.sum() if load.sum() > 0 else np.nan
    return np.nan


def _calc_weekend_ratio(df: pd.DataFrame) -> float:
    if "timestamp" not in df.columns or "load_kwh" not in df.columns:
        return np.nan
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["dayofweek"] = df["timestamp"].dt.dayofweek
    weekend_mask = df["dayofweek"].isin([5, 6])
    load = df["load_kwh"]
    return load[weekend_mask].sum() / load.sum() if weekend_mask.any() and load.sum() > 0 else np.nan


def _calc_seasonal_ratio(df: pd.DataFrame) -> float:
    if "timestamp" not in df.columns or "load_kwh" not in df.columns:
        return np.nan
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["month"] = df["timestamp"].dt.month
    summer = df["month"].isin([6, 7, 8])
    winter = df["month"].isin([12, 1, 2])
    load = df["load_kwh"]
    if summer.any() and winter.any():
        winter_mean = load[winter].mean()
        if winter_mean > 0:
            return load[summer].mean() / winter_mean
    return np.nan


CUSTOM_DF_FEATURES: Dict[str, Callable[[pd.DataFrame], float]] = {
    "self_consumption_ratio": _calc_self_consumption,
    "load_pv_correlation": _calc_load_pv_corr,
    "temporal__peak_load_ratio": _calc_peak_load_ratio,
    "temporal__weekend_load_ratio": _calc_weekend_ratio,
    "temporal__summer_winter_ratio": _calc_seasonal_ratio,
}


# -----------------------------------------------------------------------------
# Extraktion: Config (Daten) + dieses Modul (Logik)
# -----------------------------------------------------------------------------

def extract_column_features(
    df: pd.DataFrame,
    column: str,
    spec: Dict[str, Any],
    prefix: str = "",
) -> Dict[str, float]:
    """
    Extrahiert Features für eine Spalte anhand einer Spec aus der Config.
    spec: {"stats": [...], "percentiles": [...], "custom": [names], "skip_if_empty": bool}
    """
    features: Dict[str, float] = {}
    if column not in df.columns:
        return features

    series = df[column].dropna()
    skip = spec.get("skip_if_empty", True)
    if len(series) == 0 and skip:
        return features

    feat_prefix = f"{prefix}{column}" if prefix else column

    for stat in spec.get("stats", []):
        if stat in STAT_FUNCTIONS:
            try:
                features[f"{feat_prefix}_{stat}"] = STAT_FUNCTIONS[stat](series)
            except Exception:
                features[f"{feat_prefix}_{stat}"] = np.nan

    for p in spec.get("percentiles", []):
        try:
            features[f"{feat_prefix}_p{p}"] = np.percentile(series, p)
        except Exception:
            features[f"{feat_prefix}_p{p}"] = np.nan

    for name in spec.get("custom", []):
        if name in CUSTOM_COLUMN_AGGREGATIONS:
            try:
                features[f"{feat_prefix}_{name}"] = CUSTOM_COLUMN_AGGREGATIONS[name](series)
            except Exception:
                features[f"{feat_prefix}_{name}"] = np.nan

    return features


def extract_all_from_config(
    df: pd.DataFrame,
    column_specs: Dict[str, Dict[str, Any]],
    df_feature_names: List[str],
) -> Dict[str, float]:
    """
    Extrahiert alle in der Config definierten Zeitreihen-Features.
    column_specs / df_feature_names kommen aus config.TIMESERIES_COLUMN_SPECS
    bzw. config.TIMESERIES_DF_FEATURE_NAMES.
    """
    all_features: Dict[str, float] = {}

    for column, spec in column_specs.items():
        feats = extract_column_features(df, column, spec)
        all_features.update(feats)

    for name in df_feature_names:
        if name in CUSTOM_DF_FEATURES:
            try:
                all_features[name] = CUSTOM_DF_FEATURES[name](df)
            except Exception:
                all_features[name] = np.nan

    return all_features


def list_all_features(
    column_specs: Dict[str, Dict[str, Any]],
    df_feature_names: List[str],
) -> Dict[str, List[str]]:
    """Listet alle konfigurierten Feature-Namen (ohne DataFrame)."""
    column_features: List[str] = []
    for column, spec in column_specs.items():
        for stat in spec.get("stats", []):
            if stat in STAT_FUNCTIONS:
                column_features.append(f"{column}_{stat}")
        for p in spec.get("percentiles", []):
            column_features.append(f"{column}_p{p}")
        for name in spec.get("custom", []):
            if name in CUSTOM_COLUMN_AGGREGATIONS:
                column_features.append(f"{column}_{name}")

    return {
        "column_features": sorted(column_features),
        "custom_features": sorted(df_feature_names),
        "total": len(column_features) + len(df_feature_names),
    }
