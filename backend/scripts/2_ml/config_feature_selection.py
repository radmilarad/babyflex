"""
Config Feature-Auswahl – eine Feature-Liste pro Target
======================================================

Quelle der Wahrheit für „welche Features pro Modell“: FEATURE_SETS_PER_TARGET.
Training (Step 3) liest von hier bzw. aus artifacts/features/<target>/selected_feature_list.txt.
2_feature_selection.py kann mit --correlations --use-selected --target SPALTE die
Korrelationsmatrix für die jeweilige Target-Liste anzeigen.

Keys: die drei Target-Spalten plus target_peak_shaving_benefit_peak_usage_hours (4. Modell, Sondermodell).
Wert None = alle Features aus der Matrix; Liste = Whitelist (Namen wie in
2_ml/artifacts/features/feature_list.txt). Threshold und Output-Dir für Sondermodell: config_models.py.
"""

from typing import Dict, Optional, List

from .config_models import TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS

# Key = Target-Spaltenname oder TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS (4. Modell, Sondermodell). Wert None = alle Features; Liste = Whitelist.
FEATURE_SETS_PER_TARGET: Dict[str, Optional[List[str]]] = {
    "target_peak_shaving_benefit": [
        "ts__usage_hours",
        "static_grid_fees",
        "grid_fee_max_load_peak",
        "list_battery_usable_max_state",
        "ts__consumption_load_kwh_peak_to_mean",
        "ts__consumption_load_kwh_mean",
    ],
    "target_energy_procurement_optimization": [
        "pv_annual_total",
        "pv_consumed_percentage",
        "ts__consumption_load_kwh_mean",
        "ts__consumption_pv_pearson",
        "list_battery_usable_max_state",
        "battery_usable_per_sum_pv",
    ],
    "target_trading_revenue": [
        "ts__consumption_load_kwh_mean",
        "ts__consumption_da_pearson",
        "pv_annual_total",
        "list_battery_usable_max_state",
        "static_grid_fees",
    ],
    # 4. Modell: Sondermodell (usage_hours > PEAK_USAGE_HOURS_THRESHOLD)
    TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS: [
        "ts__usage_hours",
        "static_grid_fees",
        "grid_fee_max_load_peak",
        "list_battery_usable_max_state",
        "ts__consumption_load_kwh_peak_to_mean",
        "ts__consumption_load_kwh_mean",
        "pv_annual_total",
    ],
}
