"""
ML Config – zentrale Eingaben (nur Daten)
=========================================

Alle relevanten Konfigurationen für Extraction und Training an einem Ort.
Nur Listen, Dicts, Strings, Zahlen – keine Logik.

- EXTRACTION: KPI-Listen, Timeseries-Specs (welche Features gebaut werden)
- TRAINING: Modelltyp, CV, Pfade, Hyperparameter-Grids
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


# =============================================================================
# EXTRACTION – KPI (Datenquelle: kpi_summary)
# =============================================================================

class ExtractionType(Enum):
    ABSOLUTE = "absolute"
    DELTA = "delta"
    DELTA_PERCENT = "delta_pct"
    RATIO = "ratio"


@dataclass
class KPIFeatureConfig:
    """Nur Daten: Listen der KPI-Namen und Prefixes."""
    absolute_kpis: List[str] = field(default_factory=list)
    delta_kpis: List[str] = field(default_factory=list)
    delta_percent_kpis: List[str] = field(default_factory=list)
    ratio_kpis: List[str] = field(default_factory=list)
    target_kpis: List[str] = field(default_factory=list)
    absolute_prefix: str = "kpi_"
    delta_prefix: str = "delta_"
    delta_pct_prefix: str = "delta_pct_"
    ratio_prefix: str = "ratio_"


KPI_ABSOLUTE = [
    "annual_consumption_load_0_energy",
    "annual_total_generated_energy",
    "annual_total_grid_load",
    "annual_total_grid_load_positive",
    "annual_total_grid_load_negative",
    "max_abs_grid_load_pos_kW",
    "max_abs_grid_load_neg_kW",
    "max_baseline_grid_load",
    "pv_annual_total",
    "pv_consumed_directly",
    "pv_consumed_percentage",
    "pv_sold",
    "pv_stored",
    "battery_0_max_state",
    "battery_0_max_positive_load",
    "battery_0_max_negative_load",
    "battery_0_num_annual_cycles",
    "list_battery_proportion_hourly_max_load",
    "annual_usage_hours_da",
    "annual_usage_hours_ia",
    "annual_usage_hours_ic",
]
KPI_DELTA = [
    "annual_total_energy_trade_cost",
    "annual_total_energy_trade_cost_da",
    "annual_total_energy_trade_cost_ia",
    "annual_total_energy_trade_cost_ic",
    "annual_total_grid_fee_cost",
    "annual_total_grid_fee_cost_da",
    "annual_total_grid_fee_cost_ia",
    "annual_total_grid_fee_cost_ic",
    "annual_total_grid_fee_cost_peak_load",
    "annual_peak_load_grid_fee_cost_da",
    "annual_peak_load_grid_fee_cost_ia",
    "annual_peak_load_grid_fee_cost_ic",
    "avg_price_bought_da",
    "avg_price_bought_ia",
    "avg_price_bought_ic",
    "avg_price_sold_da",
    "avg_price_sold_ia",
    "avg_price_sold_ic",
    "annual_total_grid_load_cost",
]
KPI_DELTA_PCT = [
    "annual_total_energy_trade_cost",
    "annual_total_grid_fee_cost",
    "annual_total_grid_fee_cost_ic",
]
KPI_RATIO = [
    "max_load_for_fee_calculation_ic",
    "max_load_in_peak_times_ic",
    "annual_peak_maximum_grid_load_kW_ic",
]
KPI_TARGETS = [
    "peak_shaving_benefit",
    "energy_procurement_optimization",
    "trading_revenue",
]

DEFAULT_KPI_CONFIG = KPIFeatureConfig(
    absolute_kpis=KPI_ABSOLUTE.copy(),
    delta_kpis=KPI_DELTA.copy(),
    delta_percent_kpis=KPI_DELTA_PCT.copy(),
    ratio_kpis=KPI_RATIO.copy(),
    target_kpis=KPI_TARGETS.copy(),
)


# =============================================================================
# EXTRACTION – Timeseries (Datenquelle: Zeitreihen-CSVs)
# =============================================================================

TIMESERIES_COLUMN_SPECS: Dict[str, Dict[str, Any]] = {
    "load_kwh": {
        "stats": ["mean", "std", "min", "max", "sum"],
        "percentiles": [10, 25, 50, 75, 90, 95],
        "custom": ["peak_to_mean", "cv", "iqr", "skewness"],
        "skip_if_empty": True,
    },
    "soc_percent": {
        "stats": ["mean", "std", "min", "max"],
        "percentiles": [10, 50, 90],
        "custom": ["time_below_20pct", "time_above_80pct", "cycles_equivalent", "range"],
        "skip_if_empty": True,
    },
    "power_kw": {
        "stats": ["mean", "std", "min", "max"],
        "percentiles": [],
        "custom": ["charge_energy", "discharge_energy", "reversals", "utilization"],
        "skip_if_empty": True,
    },
    "grid_import_kwh": {
        "stats": ["sum", "max", "mean"],
        "percentiles": [95],
        "custom": ["peak_to_average"],
        "skip_if_empty": True,
    },
    "grid_export_kwh": {
        "stats": ["sum", "max", "mean"],
        "percentiles": [],
        "custom": ["export_ratio"],
        "skip_if_empty": True,
    },
    "generation_kwh": {
        "stats": ["sum", "max", "mean"],
        "percentiles": [],
        "custom": ["capacity_factor", "zero_generation_ratio"],
        "skip_if_empty": True,
    },
    "price_eur_mwh": {
        "stats": ["mean", "std", "min", "max"],
        "percentiles": [10, 25, 50, 75, 90],
        "custom": ["price_spread", "price_volatility"],
        "skip_if_empty": True,
    },
}

TIMESERIES_DF_FEATURE_NAMES: List[str] = [
    "self_consumption_ratio",
    "load_pv_correlation",
    "temporal__peak_load_ratio",
    "temporal__weekend_load_ratio",
    "temporal__summer_winter_ratio",
]


# =============================================================================
# TRAINING – Modell, CV, Pfade
# =============================================================================

TRAINING_TARGETS = [
    "target_peak_shaving_benefit",
    "target_energy_procurement_optimization",
    "target_trading_revenue",
]

TARGET_DESCRIPTIONS = {
    "peak_shaving_benefit": "Reduction in grid fee costs from peak load reduction",
    "energy_procurement_optimization": "Savings from optimized day-ahead energy procurement",
    "trading_revenue": "Revenue from intraday and imbalance trading",
}

METADATA_COLS = {"config_id", "client_name", "run_name", "config_name", "target"}


@dataclass
class TrainingConfig:
    """Konfiguration eines Trainings-Laufs: Modelltyp, CV, Pfade."""
    targets: List[str] = field(default_factory=lambda: list(TRAINING_TARGETS))
    test_size: float = 0.2
    random_state: int = 42
    cv_folds: int = 5
    use_loo_for_small: bool = True
    small_threshold: int = 30
    default_model: str = "gradient_boosting"
    xgb_param_grid: Dict[str, Any] = field(default_factory=lambda: {
        'n_estimators': [100, 200],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.1],
        'min_child_weight': [1, 3],
        'subsample': [0.8, 1.0],
    })
    gb_param_grid: Dict[str, Any] = field(default_factory=lambda: {
        'n_estimators': [100, 200],
        'max_depth': [3, 5],
        'learning_rate': [0.05, 0.1],
        'min_samples_split': [2, 5],
    })
    rf_param_grid: Dict[str, Any] = field(default_factory=lambda: {
        'n_estimators': [100, 200],
        'max_depth': [5, 10, None],
        'min_samples_split': [2, 5],
        'min_samples_leaf': [1, 2],
    })
    ridge_param_grid: Dict[str, Any] = field(default_factory=lambda: {
        'alpha': [0.01, 0.1, 1.0, 10.0, 100.0],
    })
    models_dir: str = "2_ml/artifacts/models"
    shap_enabled: bool = True
    top_features_to_show: int = 15


DEFAULT_TRAINING_CONFIG = TrainingConfig()

# Alias für Code, der bisher training_run_config.TARGETS nutzte
TARGETS = TRAINING_TARGETS
DEFAULT_CONFIG = DEFAULT_TRAINING_CONFIG
