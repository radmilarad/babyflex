"""
KPI Feature Extractor
=====================

Liest Zielvariablen (target_kpis) aus kpi_summary.
Input-Features kommen aus direct/indirect/load-profile, nicht aus KPIs.
"""
import numpy as np
from typing import Dict, List, Tuple
import duckdb

from ..config import KPIFeatureConfig, DEFAULT_KPI_CONFIG


class KPIFeatureExtractor:
    """Liest target_kpis aus kpi_summary für ML-Targets (get_target_values)."""

    def __init__(self,
                 db_path: str = "database/battery_simulations.duckdb",
                 config: KPIFeatureConfig = None):
        self.db_path = db_path
        self.config = config or DEFAULT_KPI_CONFIG
        self._baseline_cache: Dict[int, Dict[str, float]] = {}

    def clear_cache(self):
        """Clear the baseline KPI cache."""
        self._baseline_cache.clear()

    def _get_baseline_kpis(self, run_id: int) -> Dict[str, float]:
        """Get baseline KPIs for a run (cached)."""
        if run_id in self._baseline_cache:
            return self._baseline_cache[run_id]

        with duckdb.connect(self.db_path, read_only=True) as conn:
            baseline = conn.execute("""
                SELECT config_id
                FROM battery_configs
                WHERE run_id = ?
                  AND (is_baseline = TRUE
                       OR battery_capacity_kwh = 0
                       OR LOWER(config_name) LIKE '%0kwh%'
                       OR LOWER(config_name) = '0kwh')
                ORDER BY is_baseline DESC, battery_capacity_kwh ASC NULLS FIRST
                LIMIT 1
            """, [run_id]).fetchone()

            if not baseline:
                self._baseline_cache[run_id] = {}
                return {}

            baseline_config_id = baseline[0]
            kpis = conn.execute("""
                SELECT kpi_name, kpi_value
                FROM kpi_summary
                WHERE config_id = ?
            """, [baseline_config_id]).df()
            baseline_kpis = dict(zip(kpis['kpi_name'], kpis['kpi_value']))
            self._baseline_cache[run_id] = baseline_kpis
            return baseline_kpis

    def _get_config_kpis(self, config_id: int) -> Tuple[Dict[str, float], int]:
        """Get KPIs for a config and its run_id."""
        with duckdb.connect(self.db_path, read_only=True) as conn:
            result = conn.execute("""
                SELECT run_id FROM battery_configs WHERE config_id = ?
            """, [config_id]).fetchone()

            if not result:
                return {}, -1

            run_id = result[0]
            kpis = conn.execute("""
                SELECT kpi_name, kpi_value
                FROM kpi_summary
                WHERE config_id = ?
            """, [config_id]).df()
            return dict(zip(kpis['kpi_name'], kpis['kpi_value'])), run_id

    def _safe_float(self, value) -> float:
        """Safely convert value to float."""
        if value is None or value is False:
            return np.nan
        try:
            return float(value)
        except (ValueError, TypeError):
            return np.nan

    def get_target_values(self, config_id: int) -> Dict[str, float]:
        """Get target KPI values for ML training."""
        config_kpis, _ = self._get_config_kpis(config_id)

        targets = {}
        for kpi_name in self.config.target_kpis:
            value = config_kpis.get(kpi_name)
            targets[f"target_{kpi_name}"] = self._safe_float(value)

        return targets

    def get_kpi_values(self, config_id: int, kpi_names: List[str]) -> Dict[str, float]:
        """
        Liest beliebige KPI-Namen aus kpi_summary für diese config_id.
        Für DIRECT_INPUT_NAMES, die aus den KPI-Sheets kommen (kpi_name).
        """
        config_kpis, _ = self._get_config_kpis(config_id)
        return {
            name: self._safe_float(config_kpis.get(name))
            for name in kpi_names
        }

    def validate_config(self) -> Dict[str, list]:
        """Check which configured target KPIs actually exist in the database."""
        with duckdb.connect(self.db_path, read_only=True) as conn:
            available = set(conn.execute("""
                SELECT DISTINCT kpi_name FROM kpi_summary
            """).df()['kpi_name'].tolist())

        required = set(self.config.target_kpis)

        return {
            'available': sorted(required & available),
            'missing': sorted(required - available),
            'unused_in_db': sorted(available - required)
        }
