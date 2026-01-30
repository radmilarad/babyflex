"""
ML Feature Extraction
=====================

Feature extraction from battery simulation data: pipeline, store, data loader,
KPI and timeseries feature logic.

Config: 2_ml/config.py (nur Eingaben).
Logik: timeseries_aggregations.py, kpi_feature_extractor.py, feature_extractors.py.
"""

from .pipeline import FeatureExtractionPipeline, extract_features
from .feature_store import FeatureStore
from .data_loader import DuckDBLoader
from .kpi_feature_extractor import KPIFeatureExtractor
from ..config import (
    KPIFeatureConfig,
    DEFAULT_KPI_CONFIG,
    TIMESERIES_COLUMN_SPECS,
    TIMESERIES_DF_FEATURE_NAMES,
)
from .feature_extractors import (
    FeatureExtractorRegistry,
    BaseFeatureExtractor,
    ConfigBasedFeatures,
    LoadProfileFeatures,
    BatteryFeatures,
    TemporalFeatures,
    GridFeatures,
)
from .timeseries_aggregations import list_all_features as _list_all_features


def list_all_features(column_specs=None, df_feature_names=None):
    """Liste aller konfigurierten Zeitreihen-Features. Ohne Args: Default-Config."""
    cs = column_specs if column_specs is not None else TIMESERIES_COLUMN_SPECS
    dfn = df_feature_names if df_feature_names is not None else TIMESERIES_DF_FEATURE_NAMES
    return _list_all_features(cs, dfn)


__all__ = [
    "FeatureExtractionPipeline",
    "extract_features",
    "FeatureStore",
    "DuckDBLoader",
    "KPIFeatureExtractor",
    "KPIFeatureConfig",
    "DEFAULT_KPI_CONFIG",
    "TIMESERIES_COLUMN_SPECS",
    "TIMESERIES_DF_FEATURE_NAMES",
    "FeatureExtractorRegistry",
    "BaseFeatureExtractor",
    "ConfigBasedFeatures",
    "LoadProfileFeatures",
    "BatteryFeatures",
    "TemporalFeatures",
    "GridFeatures",
    "list_all_features",
]
