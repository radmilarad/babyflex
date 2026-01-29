"""
Benefit Calculator Module
=========================

Calculates derived outcome variables (benefits) for battery configurations
by comparing them to the 0-battery baseline case within each run.

Outcome Variables (3 target variables for ML):
    1. peak_shaving_benefit: 
       Reduction in grid fee costs from peak load reduction.
       Formula: baseline(annual_total_grid_fee_cost_ic) - battery(annual_total_grid_fee_cost_ic)
       
    2. energy_procurement_optimization:
       Savings from optimized day-ahead energy procurement.
       Formula: baseline(annual_total_energy_trade_cost_da) - battery(annual_total_energy_trade_cost_da)
       
    3. trading_revenue:
       Revenue from intraday (IA) and imbalance/continuous (IC) trading.
       Formula: sum of (baseline - battery) for annual_total_energy_trade_cost_ia 
                and annual_total_energy_trade_cost_ic

All benefits are calculated as: baseline_value - battery_value
(so positive values indicate savings/revenue)

Usage:
    from benefit_calculator import BenefitCalculator
    from battery_db import BatteryDatabase
    
    db = BatteryDatabase()
    calc = BenefitCalculator(db)
    
    # Calculate benefits for all configs
    benefits_df = calc.calculate_all_benefits()
    
    # Or just for one run
    benefits_df = calc.calculate_benefits_for_run(client_name, run_name)
    
    # Save to database for ML training
    calc.save_benefits_as_kpis(benefits_df)
"""

import warnings
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from battery_db import BatteryDatabase


# Define which KPIs to use for calculating each benefit type
# Only 3 benefits as specified:
# 1. peak_shaving_benefit: grid fee savings from peak reduction
# 2. energy_procurement_optimization: day-ahead energy cost savings  
# 3. trading_revenue: revenue from intraday + imbalance trading

BENEFIT_DEFINITIONS = {
    # Peak Shaving Benefit: Reduction in grid fees (IC optimization)
    # Formula: baseline(annual_total_grid_fee_cost_ic) - battery(annual_total_grid_fee_cost_ic)
    'peak_shaving_benefit': {
        'description': 'Reduction in total grid fee costs from peak shaving',
        'baseline_kpi': 'annual_total_grid_fee_cost_ic',
        'calculation': 'baseline - battery',
        'unit': 'EUR/year'
    },
    
    # Energy Procurement Optimization: Day-ahead energy cost savings
    # Formula: baseline(annual_total_energy_trade_cost_da) - battery(annual_total_energy_trade_cost_da)
    'energy_procurement_optimization': {
        'description': 'Savings from optimized day-ahead energy procurement',
        'baseline_kpi': 'annual_total_energy_trade_cost_da',
        'calculation': 'baseline - battery',
        'unit': 'EUR/year'
    },
    
    # Trading Revenue: Computed from IA + IC trading benefits
    # This is a composite benefit calculated separately (not from a single KPI)
    # Formula: (diff_da + diff_ia + diff_ic) + peak_shaving - energy_procurement - peak_shaving
    #        = diff_ia + diff_ic (the IA and IC portions)
    'trading_revenue': {
        'description': 'Revenue from intraday and imbalance/continuous trading',
        'is_composite': True,  # Special flag for composite calculation
        'component_kpis': [
            'annual_total_energy_trade_cost_ia',
            'annual_total_energy_trade_cost_ic'
        ],
        'calculation': 'baseline - battery',  # For each component
        'unit': 'EUR/year'
    }
}


class BenefitCalculator:
    """Calculator for battery benefit metrics relative to baseline.
    
    For each run, identifies the 0-battery baseline case and calculates
    benefit KPIs as differences from that baseline for all other configs.
    
    Note: Baseline cases (0 battery) are excluded from the output since
    they serve only as the reference point and don't have meaningful
    benefit values (they would all be 0).
    """
    
    def __init__(self, db: BatteryDatabase):
        """
        Initialize the benefit calculator.
        
        Args:
            db: BatteryDatabase instance
        """
        self.db = db
        self.benefit_definitions = BENEFIT_DEFINITIONS
    
    def get_baseline_for_run(self, run_id: int) -> Optional[int]:
        """Get the baseline (0 battery) config_id for a run.
        
        Args:
            run_id: Run ID to find baseline for
            
        Returns:
            config_id of baseline, or None if not found
        """
        result = self.db.conn.execute("""
            SELECT config_id 
            FROM battery_configs 
            WHERE run_id = ? AND is_baseline = TRUE
            ORDER BY config_id
            LIMIT 1
        """, [run_id]).fetchone()
        
        if result:
            return result[0]
        
        # Fallback: look for config with 0 capacity or '0' in name
        result = self.db.conn.execute("""
            SELECT config_id 
            FROM battery_configs 
            WHERE run_id = ? 
              AND (battery_capacity_kwh = 0 
                   OR battery_capacity_kwh IS NULL
                   OR LOWER(config_name) LIKE '%0kwh%'
                   OR LOWER(config_name) LIKE '%0_kwh%'
                   OR LOWER(config_name) = '0kwh')
            ORDER BY battery_capacity_kwh NULLS FIRST
            LIMIT 1
        """, [run_id]).fetchone()
        
        return result[0] if result else None
    
    def get_kpi_values(self, config_id: int) -> Dict[str, float]:
        """Get all KPI values for a config as a dictionary.
        
        Args:
            config_id: Battery config ID
            
        Returns:
            Dict mapping kpi_name -> kpi_value
        """
        result = self.db.conn.execute("""
            SELECT kpi_name, kpi_value 
            FROM kpi_summary 
            WHERE config_id = ?
        """, [config_id]).df()
        
        return dict(zip(result['kpi_name'], result['kpi_value']))
    
    def calculate_benefits(
        self, 
        baseline_kpis: Dict[str, float], 
        battery_kpis: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate all benefit metrics.
        
        Args:
            baseline_kpis: KPI values for baseline (0 battery) case
            battery_kpis: KPI values for battery case
            
        Returns:
            Dict mapping benefit_name -> benefit_value
        """
        benefits = {}
        
        for benefit_name, definition in self.benefit_definitions.items():
            # Check if this is a composite benefit (like trading_revenue)
            if definition.get('is_composite', False):
                # Composite benefit: sum of multiple KPI differences
                component_kpis = definition.get('component_kpis', [])
                total_benefit = 0.0
                all_valid = True
                
                for kpi_name in component_kpis:
                    baseline_val = baseline_kpis.get(kpi_name)
                    battery_val = battery_kpis.get(kpi_name)
                    
                    # Skip if either value is missing or False
                    if baseline_val is None or battery_val is None:
                        all_valid = False
                        break
                    if baseline_val is False or battery_val is False:
                        all_valid = False
                        break
                    
                    try:
                        baseline_val = float(baseline_val)
                        battery_val = float(battery_val)
                    except (ValueError, TypeError):
                        all_valid = False
                        break
                    
                    # Calculate difference based on formula
                    if definition['calculation'] == 'baseline - battery':
                        total_benefit += baseline_val - battery_val
                    elif definition['calculation'] == 'battery - baseline':
                        total_benefit += battery_val - baseline_val
                
                benefits[benefit_name] = total_benefit if all_valid else np.nan
            else:
                # Simple benefit: single KPI difference
                baseline_kpi = definition['baseline_kpi']
                
                # Get values (with fallback to NaN)
                baseline_val = baseline_kpis.get(baseline_kpi)
                battery_val = battery_kpis.get(baseline_kpi)
                
                # Skip if either value is missing or False (your KPIs use False for N/A)
                if baseline_val is None or battery_val is None:
                    benefits[benefit_name] = np.nan
                    continue
                if baseline_val is False or battery_val is False:
                    benefits[benefit_name] = np.nan
                    continue
                    
                try:
                    baseline_val = float(baseline_val)
                    battery_val = float(battery_val)
                except (ValueError, TypeError):
                    benefits[benefit_name] = np.nan
                    continue
                
                # Calculate benefit based on formula
                if definition['calculation'] == 'baseline - battery':
                    benefits[benefit_name] = baseline_val - battery_val
                elif definition['calculation'] == 'battery - baseline':
                    benefits[benefit_name] = battery_val - baseline_val
                else:
                    benefits[benefit_name] = np.nan
        
        return benefits
    
    def calculate_benefits_for_run(
        self, 
        client_name: str, 
        run_name: str,
        include_baseline: bool = False
    ) -> pd.DataFrame:
        """Calculate benefits for all configs in a run.
        
        Args:
            client_name: Client name
            run_name: Run name
            include_baseline: Whether to include baseline (with 0 benefits)
            
        Returns:
            DataFrame with config info and calculated benefits
        """
        # Get run_id
        run_id = self.db.get_run_id(client_name, run_name)
        if run_id is None:
            warnings.warn(f"Run not found: {client_name}/{run_name}")
            return pd.DataFrame()
        
        # Get baseline
        baseline_config_id = self.get_baseline_for_run(run_id)
        if baseline_config_id is None:
            warnings.warn(f"No baseline found for run: {client_name}/{run_name}")
            return pd.DataFrame()
        
        baseline_kpis = self.get_kpi_values(baseline_config_id)
        
        # Get all configs in this run
        configs = self.db.conn.execute("""
            SELECT config_id, config_name, battery_capacity_kwh, battery_power_kw, is_baseline
            FROM battery_configs
            WHERE run_id = ?
            ORDER BY battery_capacity_kwh
        """, [run_id]).df()
        
        rows = []
        for _, config in configs.iterrows():
            config_id = config['config_id']
            
            # Skip baseline unless requested
            if config['is_baseline'] and not include_baseline:
                continue
            
            # Get battery KPIs
            battery_kpis = self.get_kpi_values(config_id)
            
            # Calculate benefits
            if config['is_baseline']:
                # Baseline has 0 benefits by definition
                benefits = {name: 0.0 for name in self.benefit_definitions}
            else:
                benefits = self.calculate_benefits(baseline_kpis, battery_kpis)
            
            row = {
                'config_id': config_id,
                'client_name': client_name,
                'run_name': run_name,
                'config_name': config['config_name'],
                'battery_capacity_kwh': config['battery_capacity_kwh'],
                'battery_power_kw': config['battery_power_kw'],
                'is_baseline': config['is_baseline'],
                'baseline_config_id': baseline_config_id,
                **benefits
            }
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def calculate_all_benefits(
        self, 
        client_name: str = None,
        include_baseline: bool = False
    ) -> pd.DataFrame:
        """Calculate benefits for all runs (optionally filtered by client).
        
        Args:
            client_name: Optional client filter
            include_baseline: Whether to include baseline cases
            
        Returns:
            DataFrame with all calculated benefits
        """
        # Get all runs
        runs = self.db.get_runs(client_name)
        
        if len(runs) == 0:
            print("No runs found in database.")
            return pd.DataFrame()
        
        all_benefits = []
        for _, run in runs.iterrows():
            print(f"  Processing: {run['client_name']}/{run['run_name']}...")
            
            benefits_df = self.calculate_benefits_for_run(
                run['client_name'], 
                run['run_name'],
                include_baseline=include_baseline
            )
            
            if len(benefits_df) > 0:
                all_benefits.append(benefits_df)
        
        if not all_benefits:
            return pd.DataFrame()
        
        return pd.concat(all_benefits, ignore_index=True)
    
    def save_benefits_as_kpis(self, benefits_df: pd.DataFrame = None):
        """Save calculated benefits back to kpi_summary table.
        
        This allows the benefits to be used like any other KPI in the ML pipeline.
        
        Args:
            benefits_df: DataFrame from calculate_all_benefits (or will compute)
        """
        if benefits_df is None:
            benefits_df = self.calculate_all_benefits(include_baseline=False)
        
        if len(benefits_df) == 0:
            print("No benefits to save.")
            return
        
        benefit_columns = list(self.benefit_definitions.keys())
        
        saved_count = 0
        for _, row in benefits_df.iterrows():
            config_id = row['config_id']
            
            for benefit_name in benefit_columns:
                value = row.get(benefit_name)
                if pd.isna(value):
                    continue
                
                unit = self.benefit_definitions[benefit_name]['unit']
                
                try:
                    self.db.conn.execute("""
                        INSERT INTO kpi_summary (config_id, kpi_name, kpi_value, kpi_unit)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT (config_id, kpi_name) DO UPDATE SET
                            kpi_value = EXCLUDED.kpi_value,
                            kpi_unit = EXCLUDED.kpi_unit
                    """, [config_id, benefit_name, float(value), unit])
                    saved_count += 1
                except Exception as e:
                    warnings.warn(f"Failed to save benefit {benefit_name} for config {config_id}: {e}")
        
        print(f"✅ Saved {saved_count} benefit KPIs to database")
    
    def get_benefit_summary(self, benefits_df: pd.DataFrame = None) -> pd.DataFrame:
        """Get summary statistics for calculated benefits.
        
        Args:
            benefits_df: DataFrame from calculate_all_benefits
            
        Returns:
            Summary DataFrame with mean, std, min, max for each benefit
        """
        if benefits_df is None:
            benefits_df = self.calculate_all_benefits()
        
        if len(benefits_df) == 0:
            return pd.DataFrame()
        
        benefit_columns = [c for c in self.benefit_definitions.keys() if c in benefits_df.columns]
        
        summary_rows = []
        for col in benefit_columns:
            values = benefits_df[col].dropna()
            summary_rows.append({
                'benefit_name': col,
                'description': self.benefit_definitions[col]['description'],
                'unit': self.benefit_definitions[col]['unit'],
                'count': len(values),
                'mean': values.mean(),
                'std': values.std(),
                'min': values.min(),
                'max': values.max()
            })
        
        return pd.DataFrame(summary_rows)
    
    def list_available_baseline_kpis(self) -> List[str]:
        """List all KPIs that are available for benefit calculations."""
        result = self.db.conn.execute("""
            SELECT DISTINCT kpi_name 
            FROM kpi_summary 
            ORDER BY kpi_name
        """).fetchall()
        return [r[0] for r in result]


def add_custom_benefit(
    name: str, 
    baseline_kpi: str = None,
    component_kpis: List[str] = None,
    calculation: str = 'baseline - battery',
    description: str = '',
    unit: str = 'EUR/year'
):
    """Add a custom benefit definition.
    
    Args:
        name: Name of the benefit (e.g., 'my_custom_benefit')
        baseline_kpi: KPI name to use for simple benefit calculation
        component_kpis: List of KPI names for composite benefit (sum of differences)
        calculation: Either 'baseline - battery' or 'battery - baseline'
        description: Human-readable description
        unit: Unit of measurement
    """
    if component_kpis:
        # Composite benefit
        BENEFIT_DEFINITIONS[name] = {
            'description': description or f'Composite benefit from {", ".join(component_kpis)}',
            'is_composite': True,
            'component_kpis': component_kpis,
            'calculation': calculation,
            'unit': unit
        }
    else:
        # Simple benefit
        BENEFIT_DEFINITIONS[name] = {
            'description': description or f'Benefit from {baseline_kpi}',
            'baseline_kpi': baseline_kpi,
            'calculation': calculation,
            'unit': unit
        }


if __name__ == "__main__":
    print("Benefit Calculator Demo")
    print("=" * 50)
    
    db = BatteryDatabase()
    calc = BenefitCalculator(db)
    
    # List available KPIs
    kpis = calc.list_available_baseline_kpis()
    print(f"\nAvailable KPIs for benefit calculations: {len(kpis)}")
    
    # Calculate benefits
    print("\nCalculating benefits for all runs...")
    benefits_df = calc.calculate_all_benefits()
    
    if len(benefits_df) > 0:
        print(f"\nCalculated benefits for {len(benefits_df)} configurations")
        
        # Show summary
        summary = calc.get_benefit_summary(benefits_df)
        print("\n=== Benefit Summary ===")
        print(summary.to_string(index=False))
        
        # Save to database
        print("\nSaving benefits to database...")
        calc.save_benefits_as_kpis(benefits_df)
    else:
        print("No benefits calculated. Check that baseline cases exist.")
    
    db.close()

