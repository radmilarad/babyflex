"""
ML Feature Extraction and Training Utilities
=============================================

This module provides tools for extracting features from battery simulation
data stored in DuckDB and preparing them for machine learning.

Key Components:
- FeatureExtractionPipeline: Main orchestration class (2_ml.extraction)
- FeatureStore: Local Parquet-based feature storage
- KPIFeatureExtractor: Extract features from KPI summaries
- FeatureExtractorRegistry: Timeseries feature extraction

Quick Start:
    from 2_ml import FeatureExtractionPipeline  # from project root; or: importlib.import_module("2_ml")
    
    # Run feature extraction
    pipeline = FeatureExtractionPipeline()
    features = pipeline.run(target_kpi="peak_shaving_benefit")
    
    # Get training data
    X, y, feature_names = pipeline.get_training_data()

Custom target_kpis:
    from 2_ml import FeatureExtractionPipeline
    from 2_ml.extraction import KPIFeatureConfig
    
    config = KPIFeatureConfig(target_kpis=["peak_shaving_benefit"])
    pipeline = FeatureExtractionPipeline(kpi_config=config)
    features = pipeline.run()

Adding New Timeseries Features:
    Eingaben: 2_ml/config.py (TIMESERIES_COLUMN_SPECS, TIMESERIES_DF_FEATURE_NAMES)
    Logik: 2_ml/extraction/timeseries_aggregations.py (CUSTOM_COLUMN_AGGREGATIONS, CUSTOM_DF_FEATURES)
"""

from .extraction import (
    FeatureExtractionPipeline,
    extract_features,
    FeatureStore,
    DuckDBLoader,
    KPIFeatureExtractor,
    KPIFeatureConfig,
    DEFAULT_KPI_CONFIG,
    TIMESERIES_COLUMN_SPECS,
    TIMESERIES_DF_FEATURE_NAMES,
    FeatureExtractorRegistry,
    BaseFeatureExtractor,
    ConfigBasedFeatures,
    LoadProfileFeatures,
    BatteryFeatures,
    TemporalFeatures,
    GridFeatures,
    list_all_features,
)

__all__ = [
    # Main pipeline
    "FeatureExtractionPipeline",
    "extract_features",
    
    # Storage
    "FeatureStore",
    
    # Data loading
    "DuckDBLoader",
    
    # KPI features
    "KPIFeatureExtractor",
    "KPIFeatureConfig",
    "DEFAULT_KPI_CONFIG",
    
    # Timeseries config (data only)
    "TIMESERIES_COLUMN_SPECS",
    "TIMESERIES_DF_FEATURE_NAMES",
    
    # Timeseries features (class-based)
    "FeatureExtractorRegistry",
    "BaseFeatureExtractor",
    "ConfigBasedFeatures",
    "LoadProfileFeatures",
    "BatteryFeatures",
    "TemporalFeatures",
    "GridFeatures",
    
    # Timeseries features (config-based)
    "list_all_features",
]
