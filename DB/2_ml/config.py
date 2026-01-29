"""
ML Config – zentrale Eingaben (nur Daten)
=========================================

Alle relevanten Konfigurationen für Extraction und Training an einem Ort.
Nur Listen, Dicts, Strings, Zahlen – keine Logik.

Input-Kategorisierung für Extraction:
  (a) Direct inputs   – z.B. Battery-Parameter, direkt verfügbar
  (b) Indirect inputs – derzeit disabled, ggf. später für PV-Simulation
  (c) Inputs derived from load profile – aus Zeitreihen abgeleitete Features

-----------------------------------------------------------------------------
REFERENZ: Welche Variablennamen du verwenden kannst
-----------------------------------------------------------------------------

(1) DIRECT INPUTS (DIRECT_INPUT_NAMES)
    Zwei Quellen – die Pipeline prüft zuerst Metadata, dann kpi_summary:

    A) Metadata (DuckDB get_all_configs): Spaltennamen exakt so:
       config_id, client_name, run_name, config_name,
       battery_capacity_kwh, battery_power_kw, battery_efficiency,
       is_baseline, timeseries_file_path, target
       → data_loader.py Zeile 39–51.

    B) KPI-Sheets (kpi_summary): KPI-Namen aus kpi_summary_*.xlsx/CSV (Spalte kpi_name).
       Alles, was nicht in A) vorkommt, wird aus kpi_summary geladen
       (z.B. list_battery_max_state, list_battery_usability, pv_annual_total).
       → Pipeline ruft kpi_extractor.get_kpi_values(config_id, fehlende Namen).

(2) TARGETS (Zielvariablen aus kpi_summary)
    Quelle: Tabelle kpi_summary, Spalte kpi_name (kommt aus kpi_summary_*.xlsx/ CSV).
    Du kannst nur KPI-Namen verwenden, die in der DB existieren.

    Verfügbare KPIs anzeigen:
      from importlib import import_module
      loader = import_module("2_ml.extraction.data_loader").DuckDBLoader("database/battery_simulations.duckdb")
      print(loader.get_available_kpis())

    In config: KPI_TARGETS / KPIFeatureConfig.target_kpis (z.B. peak_shaving_benefit).

(3) LOAD-PROFILE (Zeitreihen-Spalten für ts__-Features)
    Quelle: CSV pro Config (timeseries_file_path). Spaltennamen = erste Zeile der CSV.

    Wenn die CSV von 3_prediction/preprocess_load_and_pv.py kommt:
      timestamp_utc, grid_load_kwh, consumption_kwh

    Wenn die CSV aus Simulation/Flex kommt (z.B. flex_timeseries), typische Spalten
    laut database/schema.sql: timestamp, soc_percent, power_kw, grid_import_kwh,
    grid_export_kwh, load_kwh, generation_kwh (plus weitere je nach Export).

    In config: LOAD_PROFILE_COLUMN_SPECS – Keys müssen exakt zu den Spaltennamen
    in deinen Zeitreihen-CSVs passen (z.B. grid_load_kwh, consumption_kwh).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


# =============================================================================
# INPUT CATEGORIES (Extraction-Type-Klassen)
# =============================================================================

class InputCategory(Enum):
    """Kategorisierung der Input-Features für Extraction und Prediction."""
    DIRECT_INPUTS = "direct_inputs"
    INDIRECT_INPUTS = "indirect_inputs"   # derzeit disabled, ggf. später PV-Simulation
    LOAD_PROFILE_DERIVED = "load_profile_derived"


# =============================================================================
# (a) DIRECT INPUTS
# =============================================================================

# Feature-Namen, die als „direct inputs“ gelten (z.B. aus Metadata/Config).
DIRECT_INPUT_NAMES: List[str] = [
    "list_battery_max_state",
    "list_battery_usability",
    "list_battery_usable_max_state",
    "list_battery_efficiency",
    "list_battery_num_annual_cycles",
    "list_battery_proportion_hourly_max_load",
    "pv_annual_total",
    "pv_consumed_percentage",
]


# =============================================================================
# (b) INDIRECT INPUTS – disabled, ggf. später für PV-Simulation
# =============================================================================

INDIRECT_INPUTS_ENABLED: bool = False
INDIRECT_INPUT_NAMES: List[str] = []


# =============================================================================
# (c) INPUTS DERIVED FROM LOAD PROFILE (Zeitreihen → Stats/Customs)
# =============================================================================
# Siehe LOAD_PROFILE_COLUMN_SPECS und LOAD_PROFILE_DF_FEATURE_NAMES weiter unten.


# =============================================================================
# EXTRACTION – Targets (Zielvariablen aus kpi_summary)
# =============================================================================
# Input-Features kommen aus DIRECT_INPUT_NAMES, INDIRECT_INPUT_NAMES, LOAD_PROFILE_*.
# target_kpis = welche KPIs aus kpi_summary als Zielvariablen (target_*) gelesen werden.

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


# =============================================================================
# (c) INPUTS DERIVED FROM LOAD PROFILE – Zeitreihen-CSVs
# =============================================================================

# Spalten-Specs: welche Stats/Perzentile/Customs pro Zeitreihen-Spalte
# CSV aus Preprocessing hat 2 Wert-Spalten: grid_load_kwh, consumption_kwh
LOAD_PROFILE_COLUMN_SPECS: Dict[str, Dict[str, Any]] = {
    "grid_load_kwh": {
        "stats": ["mean", "std", "min", "max", "sum"],
        "percentiles": [10, 25, 50, 75, 90, 95],
        "custom": ["peak_to_mean", "cv", "iqr", "skewness"],
        "skip_if_empty": True,
    },
    "consumption_kwh": {
        "stats": ["mean", "std", "min", "max", "sum"],
        "percentiles": [10, 25, 50, 75, 90, 95],
        "custom": ["peak_to_mean", "cv", "iqr", "skewness"],
        "skip_if_empty": True,
    },
}

# Cross-Column-Features (Namen)
LOAD_PROFILE_DF_FEATURE_NAMES: List[str] = [
    "self_consumption_ratio",
    "load_pv_correlation",
    "temporal__peak_load_ratio",
    "temporal__weekend_load_ratio",
    "temporal__summer_winter_ratio",
]

# Alias für bestehenden Code (verweist auf load-profile-derived)
TIMESERIES_COLUMN_SPECS = LOAD_PROFILE_COLUMN_SPECS
TIMESERIES_DF_FEATURE_NAMES = LOAD_PROFILE_DF_FEATURE_NAMES


# =============================================================================
# TRAINING – Modell, CV, Pfade
# =============================================================================

TRAINING_TARGETS = [
    "target_peak_shaving_benefit",
    "target_energy_procurement_optimization",
    "target_trading_revenue",
]

TARGET_DESCRIPTIONS = {
    "peak_shaving_benefit": "Reduction in grid fee costs from peak load reduction and total grid load reduction",
    "energy_procurement_optimization": "Savings from optimized day-ahead energy procurement",
    "trading_revenue": "Revenue from intraday trading",
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
