"""
Config Modell & Training
=========================

Modelltyp-Default, Target-Definitionen, Grenzen, CV und Param-Grids.
Hier anpassen: DEFAULT_MODEL_TYPE, PEAK_SHAVING_USAGE_HOURS_MAX, TrainingConfig.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any

# peak_shaving (Target 1): nur Zeilen mit usage_hours <= diesem Wert
PEAK_SHAVING_USAGE_HOURS_MAX: float = 6000.0
PEAK_SHAVING_USAGE_HOURS_FEATURE: str = "ts__usage_hours"

# Sondermodell (Target 4): nur Zeilen mit usage_hours > diesem Threshold
PEAK_USAGE_HOURS_THRESHOLD: float = 6000.0
MODELS_DIR_PEAK_USAGE: str = "2_ml/artifacts/models_peak_usage"

# Drei Target-Spalten (Feature-Matrix)
TRAINING_TARGETS = [
    "target_peak_shaving_benefit",
    "target_energy_procurement_optimization",
    "target_trading_revenue",
]

# 4. Modell (Sondermodell): peak_shaving_benefit nur für usage_hours > PEAK_USAGE_HOURS_THRESHOLD
# Hat keine eigene Spalte; Key für Feature-Set in config_feature_selection.py
TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS: str = "target_peak_shaving_benefit_peak_usage_hours"

# Alle vier Modell-Keys – für Doku und config_feature_selection
ALL_MODEL_KEYS: List[str] = TRAINING_TARGETS + [TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS]

TARGET_DESCRIPTIONS = {
    "peak_shaving_benefit": "Reduction in grid fee costs from peak load reduction and total grid load reduction",
    "energy_procurement_optimization": "Savings from optimized day-ahead energy procurement",
    "trading_revenue": "Revenue from intraday trading",
    "target_peak_shaving_benefit_peak_usage_hours": "Peak-shaving benefit (Modell nur für usage_hours > Threshold; ersetzt peak_shaving in dem Fall)",
}

METADATA_COLS = {"config_id", "client_name", "run_name", "config_name", "target"}

# Modelltyp wenn kein --model übergeben wird
DEFAULT_MODEL_TYPE: str = "gradient_boosting"


@dataclass
class TrainingConfig:
    """Konfiguration eines Trainings-Laufs: Modelltyp, CV, Param-Grids, Pfade."""
    targets: List[str] = field(default_factory=lambda: list(TRAINING_TARGETS))
    test_size: float = 0.2
    random_state: int = 42
    cv_folds: int = 5
    use_loo_for_small: bool = True
    small_threshold: int = 30
    default_model: str = DEFAULT_MODEL_TYPE
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

TARGETS = TRAINING_TARGETS
DEFAULT_CONFIG = DEFAULT_TRAINING_CONFIG
