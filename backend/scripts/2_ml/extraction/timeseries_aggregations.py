"""
Timeseries-Feature-Logik – ausschließlich Code
==============================================

Alle Berechnungen für Zeitreihen-Features leben hier.
Config (2_ml/config_feature_extraction.py) enthält nur die Eingaben:
- welche Spalten, welche stats/percentiles/custom-Namen.

Dieses Modul liefert die Implementierung pro Namen und die
Funktionen extract_all_from_config / list_all_features.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Callable, Optional, Tuple


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
    # --- Peak-shaving oriented (depth, frequency, duration, amplitude share) ---
    "peak_to_median": lambda s: s.max() / s.median() if s.median() > 0 else 0,
    "excess_above_p95": lambda s: (s.max() - np.percentile(s, 95)) if len(s) > 0 else 0,
    "excess_above_p95_norm": lambda s: (s.max() - np.percentile(s, 95)) / s.mean() if len(s) > 0 and s.mean() > 0 else 0,
    "time_above_p90": lambda s: (s >= np.percentile(s, 90)).mean() if len(s) > 0 else 0,
    "time_above_p95": lambda s: (s >= np.percentile(s, 95)).mean() if len(s) > 0 else 0,
    "spread_p95_p50": lambda s: (np.percentile(s, 95) - np.percentile(s, 50)) / np.percentile(s, 50) if len(s) > 0 and np.percentile(s, 50) > 0 else 0,
    "spread_max_p95": lambda s: (s.max() - np.percentile(s, 95)) / np.percentile(s, 95) if len(s) > 0 and np.percentile(s, 95) > 0 else 0,
    "peak_load_share_p90": lambda s: s[s >= np.percentile(s, 90)].sum() / s.sum() if len(s) > 0 and s.sum() > 0 else 0,
    "peak_load_share_p95": lambda s: s[s >= np.percentile(s, 95)].sum() / s.sum() if len(s) > 0 and s.sum() > 0 else 0,
}


def _run_lengths_above_threshold(s: pd.Series, threshold: float) -> List[int]:
    """Lengths of contiguous runs (number of intervals) where s >= threshold."""
    above = (s >= threshold).astype(int)
    if above.sum() == 0:
        return []
    run_id = (above.diff() != 0).cumsum()
    lengths = above.groupby(run_id).sum()
    return lengths[lengths > 0].astype(int).tolist()


def _n_peak_events(s: pd.Series, p: float = 95) -> float:
    """Number of distinct contiguous runs where load >= p-th percentile."""
    if len(s) < 2:
        return 0
    th = np.percentile(s, p)
    lengths = _run_lengths_above_threshold(s, th)
    return float(len(lengths))


def _mean_peak_duration(s: pd.Series, p: float = 95) -> float:
    """Mean length (number of intervals) of runs where load >= p-th percentile."""
    if len(s) < 2:
        return 0.0
    th = np.percentile(s, p)
    lengths = _run_lengths_above_threshold(s, th)
    return float(np.mean(lengths)) if lengths else 0.0


def _max_peak_duration(s: pd.Series, p: float = 95) -> float:
    """Max length (number of intervals) of runs where load >= p-th percentile."""
    if len(s) < 2:
        return 0.0
    th = np.percentile(s, p)
    lengths = _run_lengths_above_threshold(s, th)
    return float(max(lengths)) if lengths else 0.0


CUSTOM_COLUMN_AGGREGATIONS["n_peak_events_p95"] = lambda s: _n_peak_events(s, 95)
CUSTOM_COLUMN_AGGREGATIONS["mean_peak_duration_p95"] = lambda s: _mean_peak_duration(s, 95)
CUSTOM_COLUMN_AGGREGATIONS["max_peak_duration_p95"] = lambda s: _max_peak_duration(s, 95)


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


def _get_consumption_col(df: pd.DataFrame) -> Optional[str]:
    """Resolve consumption column (consumption_load_kwh | consumption_load_0 | consumption_kwh)."""
    for c in ("consumption_load_kwh", "consumption_load_0", "consumption_kwh"):
        if c in df.columns:
            return c
    return None


def _get_pv_col(df: pd.DataFrame) -> Optional[str]:
    """Resolve PV column (pv_load_kwh | pv_load_0)."""
    for c in ("pv_load_kwh", "pv_load_0"):
        if c in df.columns:
            return c
    return None


def _get_consumption_pv_series(df: pd.DataFrame) -> Optional[Tuple[pd.Series, pd.Series]]:
    """Resolve consumption and PV columns (support consumption_load_kwh/consumption_kwh and pv_load_kwh/pv_load_0)."""
    consumption_col = _get_consumption_col(df)
    pv_col = _get_pv_col(df)
    if consumption_col is None or pv_col is None:
        return None
    cons = df[consumption_col].dropna()
    pv = df[pv_col].dropna()
    if len(cons) < 10 or len(pv) < 10:
        return None
    common = cons.index.intersection(pv.index)
    if len(common) < 10:
        return None
    return cons.loc[common], pv.loc[common]


def _safe_corr_pearson(a: pd.Series, b: pd.Series) -> float:
    """Pearson correlation; returns np.nan if either series has zero variance (avoids RuntimeWarning)."""
    if a.std() == 0 or b.std() == 0 or np.isnan(a.std()) or np.isnan(b.std()):
        return np.nan
    return float(a.corr(b))


def _safe_corr_spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman correlation; returns np.nan if either series has zero variance (avoids RuntimeWarning)."""
    ra, rb = a.rank(), b.rank()
    if ra.std() == 0 or rb.std() == 0 or np.isnan(ra.std()) or np.isnan(rb.std()):
        return np.nan
    return float(ra.corr(rb))


def _calc_consumption_pv_pearson(df: pd.DataFrame) -> float:
    pair = _get_consumption_pv_series(df)
    if pair is None:
        return np.nan
    cons, pv = pair
    return _safe_corr_pearson(cons, pv)


def _calc_consumption_pv_spearman(df: pd.DataFrame) -> float:
    pair = _get_consumption_pv_series(df)
    if pair is None:
        return np.nan
    cons, pv = pair
    return _safe_corr_spearman(cons, pv)


def _calc_consumption_pv_r2(df: pd.DataFrame) -> float:
    r = _calc_consumption_pv_pearson(df)
    if np.isnan(r):
        return np.nan
    return float(r * r)


_price_da_cache: Optional[pd.DataFrame] = None


def _load_price_da() -> pd.DataFrame:
    """Load DA price series once (timestamp_utc, value). Tries path relative to this file, then 2_ml/extraction/price_data."""
    global _price_da_cache
    if _price_da_cache is not None:
        return _price_da_cache
    base = Path(__file__).resolve().parent
    candidates = [
        base / "price_data" / "load_price_da.csv",
        base.parent.parent / "2_ml" / "extraction" / "price_data" / "load_price_da.csv",
    ]
    path = None
    for p in candidates:
        if p.exists():
            path = p
            break
    if path is None:
        _price_da_cache = pd.DataFrame()
        return _price_da_cache
    try:
        df = pd.read_csv(path)
        if "timestamp_utc" not in df.columns or "value" not in df.columns:
            _price_da_cache = pd.DataFrame()
            return _price_da_cache
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
        df = df[["timestamp_utc", "value"]].dropna()
        _price_da_cache = df
        return _price_da_cache
    except Exception:
        _price_da_cache = pd.DataFrame()
        return _price_da_cache


def _align_consumption_da(df: pd.DataFrame, consumption_col: str):
    """Align consumption with DA price on 15min timestamps (UTC). Returns (cons_series, price_series) or (None, None)."""
    price_df = _load_price_da()
    if price_df.empty or consumption_col not in df.columns or "timestamp_utc" not in df.columns:
        return None, None
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    cons = df[consumption_col].copy()
    cons.index = ts
    cons = cons.dropna()
    cons = cons[~cons.index.duplicated(keep="first")]
    cons_15 = cons.groupby(cons.index.floor("15min")).first()
    price_df = price_df.set_index("timestamp_utc")
    price_15 = price_df.groupby(price_df.index.floor("15min")).first()
    common = cons_15.index.intersection(price_15.index)
    if len(common) < 10:
        return None, None
    return cons_15.loc[common].squeeze(), price_15.loc[common]["value"].squeeze()


def _calc_consumption_da_pearson(df: pd.DataFrame) -> float:
    consumption_col = _get_consumption_col(df)
    if consumption_col is None:
        return np.nan
    cons_vals, price_vals = _align_consumption_da(df, consumption_col)
    if cons_vals is None or price_vals is None or len(cons_vals) < 10:
        return np.nan
    return _safe_corr_pearson(cons_vals, price_vals)


def _calc_consumption_da_spearman(df: pd.DataFrame) -> float:
    consumption_col = _get_consumption_col(df)
    if consumption_col is None:
        return np.nan
    cons_vals, price_vals = _align_consumption_da(df, consumption_col)
    if cons_vals is None or price_vals is None or len(cons_vals) < 10:
        return np.nan
    return _safe_corr_spearman(cons_vals, price_vals)


def _calc_consumption_da_r2(df: pd.DataFrame) -> float:
    r = _calc_consumption_da_pearson(df)
    if np.isnan(r):
        return np.nan
    return float(r * r)


def _calc_usage_hours(df: pd.DataFrame) -> float:
    """usage_hours = grid_load_total_kwh / grid_load_peak (Summe / Max von grid_load_kwh)."""
    col = _resolve_column(df, "grid_load_kwh")
    if col is None:
        return np.nan
    s = df[col].dropna()
    if len(s) == 0 or s.max() <= 0:
        return np.nan
    total, peak = s.sum(), s.max()
    return float(total / peak)


CUSTOM_DF_FEATURES: Dict[str, Callable[[pd.DataFrame], float]] = {
    "self_consumption_ratio": _calc_self_consumption,
    "load_pv_correlation": _calc_load_pv_corr,
    "temporal__peak_load_ratio": _calc_peak_load_ratio,
    "temporal__weekend_load_ratio": _calc_weekend_ratio,
    "temporal__summer_winter_ratio": _calc_seasonal_ratio,
    "consumption_pv_pearson": _calc_consumption_pv_pearson,
    "consumption_pv_spearman": _calc_consumption_pv_spearman,
    "consumption_pv_r2": _calc_consumption_pv_r2,
    "consumption_da_pearson": _calc_consumption_da_pearson,
    "consumption_da_spearman": _calc_consumption_da_spearman,
    "consumption_da_r2": _calc_consumption_da_r2,
    "usage_hours": _calc_usage_hours,
}


# -----------------------------------------------------------------------------
# Spalten-Auflösung: Config-Keys vs. tatsächliche CSV-Spalten
# -----------------------------------------------------------------------------
# Verschiedene CSVs nutzen unterschiedliche Spaltennamen:
# - consumption: consumption_load_kwh | consumption_load_0 | consumption_kwh (preprocess_load_and_pv)
# - pv: pv_load_kwh | pv_load_0
# Ohne Auflösung würden alle Spalten-Features (stats, percentiles, custom) fehlen.

LOAD_PROFILE_COLUMN_ALIASES: Dict[str, List[str]] = {
    "consumption_load_kwh": ["consumption_load_kwh", "consumption_load_0", "consumption_kwh"],
    "pv_load_kwh": ["pv_load_kwh", "pv_load_0"],
    # CSVs aus Data-Scraping (timeseries_loader) haben ic_grid_load → grid_load_kwh in DB
    "grid_load_kwh": ["grid_load_kwh", "ic_grid_load"],
}


def _resolve_column(df: pd.DataFrame, config_column: str) -> Optional[str]:
    """Return the actual DataFrame column name for a config key, or None if missing."""
    candidates = LOAD_PROFILE_COLUMN_ALIASES.get(config_column, [config_column])
    for c in candidates:
        if c in df.columns:
            return c
    return None


# -----------------------------------------------------------------------------
# Extraktion: Config (Daten) + dieses Modul (Logik)
# -----------------------------------------------------------------------------

def extract_column_features(
    df: pd.DataFrame,
    column: str,
    spec: Dict[str, Any],
    prefix: str = "",
    feature_name_prefix: Optional[str] = None,
) -> Dict[str, float]:
    """
    Extrahiert Features für eine Spalte anhand einer Spec aus der Config.
    spec: {"stats": [...], "percentiles": [...], "custom": [names], "skip_if_empty": bool}
    feature_name_prefix: If set, use for feature names (e.g. consumption_load_kwh_mean)
        so output is stable even when CSV has consumption_load_0.
    """
    features: Dict[str, float] = {}
    if column not in df.columns:
        return features

    series = df[column].dropna()
    skip = spec.get("skip_if_empty", True)
    if len(series) == 0 and skip:
        return features

    name_base = feature_name_prefix if feature_name_prefix is not None else column
    feat_prefix = f"{prefix}{name_base}" if prefix else name_base

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
    Config-Keys (z.B. consumption_load_kwh) werden auf tatsächliche CSV-Spalten
    (z.B. consumption_load_0) gemappt, damit alle Spalten-Features anfallen.
    """
    all_features: Dict[str, float] = {}

    for config_column, spec in column_specs.items():
        actual_column = _resolve_column(df, config_column)
        if actual_column is None:
            continue
        feats = extract_column_features(
            df, actual_column, spec,
            feature_name_prefix=config_column,
        )
        all_features.update(feats)

    for name in df_feature_names:
        if name in CUSTOM_DF_FEATURES:
            try:
                all_features[name] = CUSTOM_DF_FEATURES[name](df)
            except Exception:
                all_features[name] = np.nan

    return all_features


def extract_df_features_only(df: pd.DataFrame, feature_names: List[str]) -> Dict[str, float]:
    """
    Berechnet nur die angegebenen CUSTOM_DF_FEATURES (z.B. usage_hours).
    Nützlich um einzelne Spalten in der Feature-Matrix nachzuziehen ohne Voll-Extraktion.
    feature_names: Namen ohne Prefix, z.B. ["usage_hours"].
    """
    out: Dict[str, float] = {}
    for name in feature_names:
        if name in CUSTOM_DF_FEATURES:
            try:
                out[name] = CUSTOM_DF_FEATURES[name](df)
            except Exception:
                out[name] = np.nan
    return out


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
