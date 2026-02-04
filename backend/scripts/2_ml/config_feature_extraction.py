"""
Config Feature-Extraktion (Step 1) – nicht anfassen
====================================================

Definiert, welche Features in 1_extract_features berechnet und in der
Feature-Matrix gespeichert werden. Wird nur von der Extraction-Pipeline
Für Feature-Auswahl beim Training
→ config_feature_selection.py (drei Targets + 4. Modell target_peak_shaving_benefit_peak_usage_hours).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class InputCategory(Enum):
    """Kategorisierung der Input-Features für Extraction und Prediction."""
    DIRECT_INPUTS = "direct_inputs"
    INDIRECT_INPUTS = "indirect_inputs"
    LOAD_PROFILE_DERIVED = "load_profile_derived"


DIRECT_INPUT_NAMES: List[str] = [
    "list_battery_usable_max_state",
    "list_battery_num_annual_cycles",
    "list_battery_proportion_hourly_max_load",
    "pv_annual_total",
    "pv_consumed_percentage",
    "static_grid_fees",
    "grid_fee_max_load_peak",
]

INDIRECT_INPUTS_ENABLED: bool = False
INDIRECT_INPUT_NAMES: List[str] = []


@dataclass
class KPIFeatureConfig:
    """Welche KPIs aus kpi_summary als Zielvariablen (target_*) gelesen werden."""
    target_kpis: List[str] = field(default_factory=list)


KPI_TARGETS = [
    "peak_shaving_benefit",
    "energy_procurement_optimization",
    "trading_revenue",
]

DEFAULT_KPI_CONFIG = KPIFeatureConfig(target_kpis=KPI_TARGETS.copy())


PEAK_SHAVING_CUSTOM: List[str] = [
    "peak_to_mean", "peak_to_median", "cv", "iqr", "skewness",
    "excess_above_p95", "excess_above_p95_norm", "time_above_p90", "time_above_p95",
    "spread_p95_p50", "spread_max_p95", "peak_load_share_p90", "peak_load_share_p95",
    "n_peak_events_p95", "mean_peak_duration_p95", "max_peak_duration_p95",
]

LOAD_PROFILE_COLUMN_SPECS: Dict[str, Dict[str, Any]] = {
    "consumption_load_kwh": {
        "stats": ["mean", "std", "min", "max", "sum"],
        "percentiles": [10, 25, 50, 75, 90, 95],
        "custom": PEAK_SHAVING_CUSTOM,
        "skip_if_empty": True,
    },
    "pv_load_kwh": {
        "stats": ["mean", "std", "min", "max", "sum"],
        "percentiles": [10, 25, 50, 75, 90, 95],
        "custom": ["peak_to_mean", "cv", "iqr", "skewness"],
        "skip_if_empty": True,
    },
}

LOAD_PROFILE_DF_FEATURE_NAMES: List[str] = [
    "consumption_pv_pearson",
    "consumption_pv_spearman",
    "consumption_pv_r2",
    "consumption_da_pearson",
    "consumption_da_spearman",
    "consumption_da_r2",
    "usage_hours",
]

RATIO_FEATURES: List[Dict[str, str]] = [
    {"name": "battery_usable_per_sum_pv", "numerator": "list_battery_usable_max_state", "denominator_sum_column": "pv_load_kwh"},
    {"name": "battery_usable_per_sum_consumption", "numerator": "list_battery_usable_max_state", "denominator_sum_column": "consumption_load_kwh"},
]

PRICE_DATA_DA_PATH: str = "extraction/price_data/load_price_da.csv"
PRICE_DATA_IA_PATH: str = "extraction/price_data/load_price_ia.csv"
PRICE_DATA_IC_PATH: str = "extraction/price_data/load_price_ic.csv"

TIMESERIES_COLUMN_SPECS = LOAD_PROFILE_COLUMN_SPECS
TIMESERIES_DF_FEATURE_NAMES = LOAD_PROFILE_DF_FEATURE_NAMES
