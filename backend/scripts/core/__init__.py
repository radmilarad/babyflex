"""
Core – DB und Benefit-Berechnung
================================

BatteryDatabase: DuckDB-Schnittstelle (Schema, Clients, Runs, Configs, KPIs).
BenefitCalculator: Abgeleitete Zielvariablen (peak_shaving_benefit, etc.).
"""

from .battery_db import BatteryDatabase, get_db
from .benefit_calculator import BenefitCalculator, BENEFIT_DEFINITIONS

__all__ = [
    "BatteryDatabase",
    "get_db",
    "BenefitCalculator",
    "BENEFIT_DEFINITIONS",
]
