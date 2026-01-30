"""
Data Loader
===========

Interfaces with DuckDB to load battery simulation data.
Handles lazy loading of timeseries one at a time for memory efficiency.
"""
import duckdb
import pandas as pd
from pathlib import Path
from typing import Generator, Tuple, Optional


class DuckDBLoader:
    """Load battery simulation data from DuckDB."""
    
    def __init__(self, 
                 db_path: str = "database/battery_simulations.duckdb",
                 data_root: str = "data"):
        self.db_path = db_path
        self.data_root = Path(data_root)
    
    def get_all_configs(self, 
                        target_kpi: str,
                        client_filter: str = None,
                        include_baseline: bool = False) -> pd.DataFrame:
        """
        Get all battery configurations with metadata and target KPI.
        
        Args:
            target_kpi: KPI to use as target variable
            client_filter: Optional client name to filter by
            include_baseline: Whether to include 0-battery baseline cases
        
        Returns:
            DataFrame with config metadata
        """
        with duckdb.connect(self.db_path, read_only=True) as conn:
            query = """
                SELECT 
                    bc.config_id,
                    c.client_name,
                    r.run_name,
                    r.run_id,
                    bc.config_name,
                    bc.battery_capacity_kwh,
                    bc.battery_power_kw,
                    bc.battery_efficiency,
                    bc.is_baseline,
                    bc.timeseries_file_path,
                    kpi.kpi_value as target
                FROM battery_configs bc
                JOIN runs r ON bc.run_id = r.run_id
                JOIN clients c ON r.client_id = c.client_id
                LEFT JOIN kpi_summary kpi 
                    ON bc.config_id = kpi.config_id 
                    AND kpi.kpi_name = ?
                WHERE 1=1
            """
            params = [target_kpi]
            
            if not include_baseline:
                query += " AND bc.is_baseline = FALSE"
            
            if client_filter:
                query += " AND c.client_name = ?"
                params.append(client_filter)
            
            query += " ORDER BY c.client_name, r.run_name, bc.battery_capacity_kwh"
            
            return conn.execute(query, params).df()
    
    def load_timeseries(self, timeseries_file_path: str) -> pd.DataFrame:
        """
        Load a single timeseries file using DuckDB's fast CSV reader.
        
        Args:
            timeseries_file_path: Relative path to the CSV file
        
        Returns:
            DataFrame with timeseries data
        """
        if not timeseries_file_path:
            return pd.DataFrame()
        
        csv_path = self.data_root / timeseries_file_path
        if not csv_path.exists():
            return pd.DataFrame()
        
        with duckdb.connect(self.db_path, read_only=True) as conn:
            try:
                # Use DuckDB's blazing fast CSV reader
                return conn.execute(f"""
                    SELECT * FROM read_csv_auto('{csv_path}')
                """).df()
            except Exception as e:
                print(f"Error loading {csv_path}: {e}")
                return pd.DataFrame()
    
    def iter_configs_with_timeseries(self, 
                                      target_kpi: str,
                                      client_filter: str = None,
                                      skip_config_ids: set = None
                                      ) -> Generator[Tuple[pd.Series, pd.DataFrame], None, None]:
        """
        Iterate over configs, yielding (metadata_row, timeseries_df) one at a time.
        Memory efficient - only one timeseries in memory at a time.
        
        Args:
            target_kpi: KPI to use as target variable
            client_filter: Optional client name filter
            skip_config_ids: Set of config_ids to skip (already processed)
        
        Yields:
            (metadata_series, timeseries_dataframe)
        """
        configs = self.get_all_configs(target_kpi, client_filter)
        
        if skip_config_ids:
            configs = configs[~configs["config_id"].isin(skip_config_ids)]
        
        for _, row in configs.iterrows():
            ts_path = row.get("timeseries_file_path")
            ts_df = self.load_timeseries(ts_path) if ts_path else pd.DataFrame()
            yield row, ts_df
    
    def get_config_count(self, 
                         target_kpi: str,
                         client_filter: str = None,
                         skip_config_ids: set = None) -> int:
        """Get total number of configs to process."""
        configs = self.get_all_configs(target_kpi, client_filter)
        if skip_config_ids:
            configs = configs[~configs["config_id"].isin(skip_config_ids)]
        return len(configs)
    
    def get_available_kpis(self) -> list:
        """Get list of all KPI names in the database."""
        with duckdb.connect(self.db_path, read_only=True) as conn:
            result = conn.execute("""
                SELECT DISTINCT kpi_name 
                FROM kpi_summary 
                ORDER BY kpi_name
            """).fetchall()
            return [r[0] for r in result]
    
    def get_clients(self) -> list:
        """Get list of all client names."""
        with duckdb.connect(self.db_path, read_only=True) as conn:
            result = conn.execute("""
                SELECT DISTINCT client_name 
                FROM clients 
                ORDER BY client_name
            """).fetchall()
            return [r[0] for r in result]
