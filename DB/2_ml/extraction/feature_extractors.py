"""
Feature Extraction Logic
========================

All timeseries feature calculations live here.
- Config (2_ml/config.py): nur Eingaben – welche Spalten, stats, custom-Namen.
- Logik für Zeitreihen-Aggregationen: 2_ml/extraction/timeseries_aggregations.py.

Neue Features: Namen in config.TIMESERIES_* eintragen, Implementierung in
timeseries_aggregations.STAT_FUNCTIONS / CUSTOM_COLUMN_AGGREGATIONS / CUSTOM_DF_FEATURES.
"""
import pandas as pd
import numpy as np
from typing import Dict, List
from abc import ABC, abstractmethod


class BaseFeatureExtractor(ABC):
    """Base class for feature extractors."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this extractor."""
        pass
    
    @abstractmethod
    def extract(self, df: pd.DataFrame) -> Dict[str, float]:
        """Extract features from a timeseries DataFrame."""
        pass


class ConfigBasedFeatures(BaseFeatureExtractor):
    """
    Extract features from config (data) + timeseries_aggregations (logic).
    Config: 2_ml/config.py (TIMESERIES_COLUMN_SPECS, TIMESERIES_DF_FEATURE_NAMES).
    """
    name = "ts"

    def extract(self, df: pd.DataFrame) -> Dict[str, float]:
        """Extract all features from config-driven timeseries aggregations."""
        try:
            from ..config import TIMESERIES_COLUMN_SPECS, TIMESERIES_DF_FEATURE_NAMES
            from .timeseries_aggregations import extract_all_from_config
            return extract_all_from_config(
                df, TIMESERIES_COLUMN_SPECS, TIMESERIES_DF_FEATURE_NAMES
            )
        except ImportError:
            return {}


class LoadProfileFeatures(BaseFeatureExtractor):
    """Extract features from load profile data."""
    
    name = "load_profile"
    
    def __init__(self, load_col: str = "load_kwh"):
        self.load_col = load_col
    
    def extract(self, df: pd.DataFrame) -> Dict[str, float]:
        if self.load_col not in df.columns:
            return {}
        
        load = df[self.load_col].dropna()
        if len(load) == 0:
            return {}
        
        features = {
            "load_mean": load.mean(),
            "load_std": load.std(),
            "load_min": load.min(),
            "load_max": load.max(),
            "load_sum": load.sum(),
            "load_peak_to_mean": load.max() / load.mean() if load.mean() > 0 else 0,
            "load_cv": load.std() / load.mean() if load.mean() > 0 else 0,  # Coefficient of variation
        }
        
        # Percentiles
        for p in [10, 25, 50, 75, 90, 95]:
            features[f"load_p{p}"] = np.percentile(load, p)
        
        return features


class BatteryFeatures(BaseFeatureExtractor):
    """Extract features from battery operation data."""
    
    name = "battery"
    
    def __init__(self, soc_col: str = "soc_percent", power_col: str = "power_kw"):
        self.soc_col = soc_col
        self.power_col = power_col
    
    def extract(self, df: pd.DataFrame) -> Dict[str, float]:
        features = {}
        
        # SOC features
        if self.soc_col in df.columns:
            soc = df[self.soc_col].dropna()
            if len(soc) > 0:
                features["soc_mean"] = soc.mean()
                features["soc_std"] = soc.std()
                features["soc_min"] = soc.min()
                features["soc_max"] = soc.max()
                
                # Cycle counting: sum of absolute SOC changes / 200
                features["cycles_equivalent"] = soc.diff().abs().sum() / 200
                
                # Time at low/high SOC
                features["time_below_20pct"] = (soc < 20).mean()
                features["time_above_80pct"] = (soc > 80).mean()
        
        # Power features
        if self.power_col in df.columns:
            power = df[self.power_col].dropna()
            if len(power) > 0:
                features["charge_energy"] = power[power > 0].sum()
                features["discharge_energy"] = power[power < 0].abs().sum()
                features["power_reversals"] = (power.diff().abs() > 0.1).sum()
        
        return features


class TemporalFeatures(BaseFeatureExtractor):
    """Extract time-based patterns."""
    
    name = "temporal"
    
    def __init__(self, timestamp_col: str = "timestamp", value_col: str = "load_kwh"):
        self.timestamp_col = timestamp_col
        self.value_col = value_col
    
    def extract(self, df: pd.DataFrame) -> Dict[str, float]:
        if self.timestamp_col not in df.columns or self.value_col not in df.columns:
            return {}
        
        df = df.copy()
        df[self.timestamp_col] = pd.to_datetime(df[self.timestamp_col])
        df["hour"] = df[self.timestamp_col].dt.hour
        df["dayofweek"] = df[self.timestamp_col].dt.dayofweek
        df["month"] = df[self.timestamp_col].dt.month
        
        features = {}
        val = df[self.value_col]
        
        # Peak vs off-peak (assuming peak = 9-17)
        peak_mask = df["hour"].between(9, 17)
        if peak_mask.any() and (~peak_mask).any():
            features["peak_load_ratio"] = val[peak_mask].sum() / val.sum() if val.sum() > 0 else 0
            features["peak_vs_offpeak"] = val[peak_mask].mean() / val[~peak_mask].mean() if val[~peak_mask].mean() > 0 else 0
        
        # Weekday vs weekend
        weekend_mask = df["dayofweek"].isin([5, 6])
        if weekend_mask.any() and (~weekend_mask).any():
            features["weekend_load_ratio"] = val[weekend_mask].sum() / val.sum() if val.sum() > 0 else 0
        
        # Seasonal patterns (if full year data)
        if df["month"].nunique() >= 6:
            summer = df["month"].isin([6, 7, 8])
            winter = df["month"].isin([12, 1, 2])
            if summer.any() and winter.any():
                features["summer_winter_ratio"] = val[summer].mean() / val[winter].mean() if val[winter].mean() > 0 else 0
        
        return features


class GridFeatures(BaseFeatureExtractor):
    """Extract grid interaction features."""
    
    name = "grid"
    
    def extract(self, df: pd.DataFrame) -> Dict[str, float]:
        features = {}
        
        if "grid_import_kwh" in df.columns:
            imports = df["grid_import_kwh"].dropna()
            features["grid_import_total"] = imports.sum()
            features["grid_import_max"] = imports.max()
        
        if "grid_export_kwh" in df.columns:
            exports = df["grid_export_kwh"].dropna()
            features["grid_export_total"] = exports.sum()
            if "generation_kwh" in df.columns:
                gen_sum = df["generation_kwh"].sum()
                features["self_consumption_ratio"] = 1 - (exports.sum() / gen_sum) if gen_sum > 0 else 0
        
        return features


class FeatureExtractorRegistry:
    """Registry of all feature extractors."""
    
    def __init__(self):
        self.extractors: List[BaseFeatureExtractor] = []
    
    def register(self, extractor: BaseFeatureExtractor):
        self.extractors.append(extractor)
        return self
    
    def extract_all(self, df: pd.DataFrame) -> Dict[str, float]:
        """Run all registered extractors and combine results."""
        all_features = {}
        for extractor in self.extractors:
            features = extractor.extract(df)
            # Prefix with extractor name to avoid collisions
            for key, value in features.items():
                all_features[f"{extractor.name}__{key}"] = value
        return all_features
    
    @classmethod
    def default(cls) -> "FeatureExtractorRegistry":
        """Create registry with default extractors."""
        registry = cls()
        # Config-based features (recommended for new features!)
        registry.register(ConfigBasedFeatures())
        # Legacy extractors (kept for backward compatibility)
        registry.register(LoadProfileFeatures())
        registry.register(BatteryFeatures())
        registry.register(TemporalFeatures())
        registry.register(GridFeatures())
        return registry
    
    @classmethod
    def config_only(cls) -> "FeatureExtractorRegistry":
        """Create registry with only config-based features (no legacy)."""
        registry = cls()
        registry.register(ConfigBasedFeatures())
        return registry
