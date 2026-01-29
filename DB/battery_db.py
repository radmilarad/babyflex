"""
Battery Simulation Database Manager
====================================
A DuckDB-based system for storing and querying battery simulation results.

Folder Structure:
    data/
    ├── Client_A/
    │   ├── Run_1/
    │   │   ├── Input/
    │   │   │   └── parameters.json
    │   │   └── Output/
    │   │       ├── kpi_summary_0battery.csv
    │   │       ├── kpi_summary_100kWh.csv
    │   │       ├── flex_timeseries_0battery.csv
    │   │       └── flex_timeseries_100kWh.csv
    │   └── Run_2/
    │       └── ...
    └── Client_B/
        └── ...
"""

import duckdb
import pandas as pd
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Union
import re


class BatteryDatabase:
    """Main database interface for battery simulation storage."""
    
    def __init__(self, db_path: str = "database/battery_simulations.duckdb"):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the DuckDB database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_root = Path("data")
        self.data_root.mkdir(exist_ok=True)
        
        self.conn = duckdb.connect(str(self.db_path))
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema from SQL file."""
        schema_path = Path("database/schema.sql")
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                # DuckDB can execute multiple statements with execute()
                sql_content = f.read()
                # Split by semicolons and execute each statement
                for statement in sql_content.split(';'):
                    statement = statement.strip()
                    if statement:
                        try:
                            self.conn.execute(statement)
                        except Exception as e:
                            # Ignore errors for CREATE IF NOT EXISTS
                            if "already exists" not in str(e).lower():
                                print(f"Warning: {e}")
        else:
            print("Warning: schema.sql not found, creating basic tables...")
            self._create_basic_schema()
    
    def _create_basic_schema(self):
        """Create basic schema if SQL file is missing."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id INTEGER PRIMARY KEY,
                client_name VARCHAR NOT NULL UNIQUE,
                description VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY,
                client_id INTEGER NOT NULL,
                run_name VARCHAR NOT NULL,
                run_description VARCHAR,
                run_date TIMESTAMP,
                input_parameters JSON,
                folder_path VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(client_id, run_name)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS battery_configs (
                config_id INTEGER PRIMARY KEY,
                run_id INTEGER NOT NULL,
                config_name VARCHAR NOT NULL,
                is_baseline BOOLEAN DEFAULT FALSE,
                battery_capacity_kwh DOUBLE,
                battery_power_kw DOUBLE,
                battery_efficiency DOUBLE,
                other_params JSON,
                kpi_file_path VARCHAR,
                timeseries_file_path VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_id, config_name)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS kpi_summary (
                kpi_id INTEGER PRIMARY KEY,
                config_id INTEGER NOT NULL,
                kpi_name VARCHAR NOT NULL,
                kpi_value DOUBLE,
                kpi_unit VARCHAR,
                UNIQUE(config_id, kpi_name)
            )
        """)
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    # =========================================================================
    # Client Management
    # =========================================================================
    
    def add_client(self, client_name: str, description: str = None, 
                   create_folder: bool = True) -> int:
        """
        Add a new client to the database.
        
        Args:
            client_name: Name of the client
            description: Optional description
            create_folder: Whether to create folder structure (default True)
            
        Returns:
            client_id of the new or existing client
        """
        if create_folder:
            # Sanitize client name for folder
            folder_name = self._sanitize_name(client_name)
            
            # Create folder
            client_folder = self.data_root / folder_name
            client_folder.mkdir(exist_ok=True)
        
        # Insert into database (use INSERT OR IGNORE pattern)
        try:
            self.conn.execute("""
                INSERT INTO clients (client_name, description)
                VALUES (?, ?)
            """, [client_name, description])
        except (duckdb.ConstraintException, Exception) as e:
            if "unique" in str(e).lower() or "constraint" in str(e).lower():
                pass  # Client already exists, that's OK
            else:
                raise
        
        result = self.conn.execute(
            "SELECT client_id FROM clients WHERE client_name = ?", 
            [client_name]
        ).fetchone()
        
        if result is None:
            raise ValueError(f"Failed to get client_id for '{client_name}'")
        return result[0]
    
    def get_clients(self) -> pd.DataFrame:
        """Get all clients."""
        return self.conn.execute("SELECT * FROM clients").df()
    
    def get_client_id(self, client_name: str) -> Optional[int]:
        """Get client ID by name."""
        result = self.conn.execute(
            "SELECT client_id FROM clients WHERE client_name = ?",
            [client_name]
        ).fetchone()
        return result[0] if result else None
    
    # =========================================================================
    # Run Management
    # =========================================================================
    
    def add_run(
        self,
        client_name: str,
        run_name: str,
        run_description: str = None,
        input_parameters: Dict[str, Any] = None,
        run_date: datetime = None
    ) -> int:
        """
        Add a new simulation run for a client.
        
        Args:
            client_name: Name of the client
            run_name: Name of the run (e.g., "Run_1", "2024_Q1_Analysis")
            run_description: Optional description
            input_parameters: Dictionary of input parameters
            run_date: Date of the simulation run
            
        Returns:
            run_id of the new or existing run
        """
        client_id = self.get_client_id(client_name)
        if client_id is None:
            client_id = self.add_client(client_name)
        
        # Create folder structure
        client_folder = self._sanitize_name(client_name)
        run_folder = self._sanitize_name(run_name)
        folder_path = f"{client_folder}/{run_folder}"
        
        full_path = self.data_root / folder_path
        (full_path / "Input").mkdir(parents=True, exist_ok=True)
        (full_path / "Output").mkdir(parents=True, exist_ok=True)
        
        # Save input parameters to JSON file
        if input_parameters:
            params_file = full_path / "Input" / "parameters.json"
            with open(params_file, 'w') as f:
                json.dump(input_parameters, f, indent=2, default=str)
        
        # Insert into database
        params_json = json.dumps(input_parameters) if input_parameters else None
        try:
            self.conn.execute("""
                INSERT INTO runs (client_id, run_name, run_description, run_date, 
                                  input_parameters, folder_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [client_id, run_name, run_description, run_date, params_json, folder_path])
        except (duckdb.ConstraintException, Exception) as e:
            if "unique" in str(e).lower() or "constraint" in str(e).lower():
                pass  # Run already exists
            else:
                raise
        
        result = self.conn.execute("""
            SELECT run_id FROM runs 
            WHERE client_id = ? AND run_name = ?
        """, [client_id, run_name]).fetchone()
        
        if result is None:
            raise ValueError(f"Failed to get run_id for '{run_name}'")
        return result[0]
    
    def _add_run_with_path(
        self,
        client_name: str,
        run_name: str,
        folder_path: str,
        input_parameters: Dict[str, Any] = None
    ) -> int:
        """
        Add a run with a specific folder path (for importing existing folders).
        Does NOT create folders - assumes they already exist.
        """
        client_id = self.get_client_id(client_name)
        if client_id is None:
            client_id = self.add_client(client_name)
        
        params_json = json.dumps(input_parameters) if input_parameters else None
        try:
            self.conn.execute("""
                INSERT INTO runs (client_id, run_name, run_description, run_date, 
                                  input_parameters, folder_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [client_id, run_name, None, None, params_json, folder_path])
        except (duckdb.ConstraintException, Exception) as e:
            if "unique" in str(e).lower() or "constraint" in str(e).lower():
                pass
            else:
                raise
        
        result = self.conn.execute("""
            SELECT run_id FROM runs 
            WHERE client_id = ? AND run_name = ?
        """, [client_id, run_name]).fetchone()
        
        if result is None:
            raise ValueError(f"Failed to get run_id for '{run_name}'")
        return result[0]
    
    def get_runs(self, client_name: str = None) -> pd.DataFrame:
        """Get all runs, optionally filtered by client."""
        if client_name:
            return self.conn.execute("""
                SELECT r.*, c.client_name 
                FROM runs r
                JOIN clients c ON r.client_id = c.client_id
                WHERE c.client_name = ?
                ORDER BY r.run_date DESC
            """, [client_name]).df()
        else:
            return self.conn.execute("""
                SELECT r.*, c.client_name 
                FROM runs r
                JOIN clients c ON r.client_id = c.client_id
                ORDER BY c.client_name, r.run_date DESC
            """).df()
    
    def get_run_id(self, client_name: str, run_name: str) -> Optional[int]:
        """Get run ID by client and run name."""
        result = self.conn.execute("""
            SELECT r.run_id FROM runs r
            JOIN clients c ON r.client_id = c.client_id
            WHERE c.client_name = ? AND r.run_name = ?
        """, [client_name, run_name]).fetchone()
        return result[0] if result else None
    
    # =========================================================================
    # Battery Configuration Management
    # =========================================================================
    
    def add_battery_config(
        self,
        client_name: str,
        run_name: str,
        config_name: str,
        is_baseline: bool = False,
        battery_capacity_kwh: float = None,
        battery_power_kw: float = None,
        battery_efficiency: float = None,
        other_params: Dict[str, Any] = None,
        kpi_file: str = None,
        timeseries_file: str = None
    ) -> int:
        """
        Add a battery configuration to a run.
        
        Args:
            client_name: Name of the client
            run_name: Name of the run
            config_name: Name of the configuration (e.g., "0_battery", "100kWh_50kW")
            is_baseline: True if this is the 0-battery baseline case
            battery_capacity_kwh: Battery capacity in kWh
            battery_power_kw: Battery power in kW
            battery_efficiency: Round-trip efficiency (0-1)
            other_params: Additional parameters as dict
            kpi_file: Filename of KPI summary CSV
            timeseries_file: Filename of timeseries CSV
            
        Returns:
            config_id of the new configuration
        """
        run_id = self.get_run_id(client_name, run_name)
        if run_id is None:
            run_id = self.add_run(client_name, run_name)
        
        # Get folder path
        folder_path = self.conn.execute(
            "SELECT folder_path FROM runs WHERE run_id = ?", [run_id]
        ).fetchone()[0]
        
        # Set file paths
        kpi_file_path = f"{folder_path}/Output/{kpi_file}" if kpi_file else None
        ts_file_path = f"{folder_path}/Output/{timeseries_file}" if timeseries_file else None
        
        # Insert into database
        params_json = json.dumps(other_params) if other_params else None
        try:
            self.conn.execute("""
                INSERT INTO battery_configs 
                (run_id, config_name, is_baseline, battery_capacity_kwh, 
                 battery_power_kw, battery_efficiency, other_params,
                 kpi_file_path, timeseries_file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [run_id, config_name, is_baseline, battery_capacity_kwh,
                  battery_power_kw, battery_efficiency, params_json,
                  kpi_file_path, ts_file_path])
        except (duckdb.ConstraintException, Exception) as e:
            if "unique" in str(e).lower() or "constraint" in str(e).lower():
                pass  # Config already exists
            else:
                raise
        
        result = self.conn.execute("""
            SELECT config_id FROM battery_configs 
            WHERE run_id = ? AND config_name = ?
        """, [run_id, config_name]).fetchone()
        
        if result is None:
            raise ValueError(f"Failed to get config_id for '{config_name}'")
        return result[0]
    
    def get_battery_configs(self, client_name: str = None, run_name: str = None) -> pd.DataFrame:
        """Get battery configurations, optionally filtered."""
        query = """
            SELECT bc.*, r.run_name, c.client_name
            FROM battery_configs bc
            JOIN runs r ON bc.run_id = r.run_id
            JOIN clients c ON r.client_id = c.client_id
        """
        params = []
        
        if client_name and run_name:
            query += " WHERE c.client_name = ? AND r.run_name = ?"
            params = [client_name, run_name]
        elif client_name:
            query += " WHERE c.client_name = ?"
            params = [client_name]
        
        query += " ORDER BY c.client_name, r.run_name, bc.battery_capacity_kwh"
        return self.conn.execute(query, params).df()
    
    # =========================================================================
    # KPI Management
    # =========================================================================
    
    def import_kpis_from_csv(self, config_id: int, csv_path: str):
        """
        Import KPIs from a CSV or Excel file into the database.
        
        Supports two formats:
        1. Standard: kpi_name,kpi_value,kpi_unit columns
        2. Two-column: first column is name, second column is value
        """
        full_path = self.data_root / csv_path
        if not full_path.exists():
            print(f"Warning: KPI file not found: {full_path}")
            return
        
        # Handle both CSV and Excel files
        try:
            if str(full_path).endswith('.xlsx') or str(full_path).endswith('.xls'):
                df = pd.read_excel(full_path)
            else:
                df = pd.read_csv(full_path)
        except Exception as e:
            print(f"Warning: Could not read KPI file {full_path}: {e}")
            return
        
        if len(df.columns) < 2:
            print(f"Warning: KPI file has less than 2 columns: {full_path}")
            return
        
        # Detect format: check if first column looks like names (strings) 
        # and second column has values
        name_col = df.columns[0]
        value_col = df.columns[1]
        
        # Check for explicit column names
        for col in df.columns:
            if 'name' in col.lower() or 'kpi' in col.lower():
                name_col = col
            elif 'value' in col.lower():
                value_col = col
        
        unit_col = next((c for c in df.columns if 'unit' in c.lower()), None)
        
        imported_count = 0
        for _, row in df.iterrows():
            kpi_name = str(row[name_col]).strip()
            raw_value = row[value_col]
            
            # Skip empty names
            if not kpi_name or kpi_name == 'nan':
                continue
            
            # Try to convert value to float, skip if not numeric
            kpi_value = None
            if pd.notna(raw_value):
                # Handle various non-numeric values
                if isinstance(raw_value, (int, float)):
                    kpi_value = float(raw_value)
                elif isinstance(raw_value, str):
                    # Skip string values like "['none']", "False", etc.
                    raw_value = raw_value.strip()
                    if raw_value.lower() in ['false', 'true', 'none', '']:
                        continue
                    if raw_value.startswith('[') or raw_value.startswith('{'):
                        continue  # Skip list/dict values
                    try:
                        kpi_value = float(raw_value)
                    except ValueError:
                        continue  # Skip non-numeric strings
                elif isinstance(raw_value, bool):
                    continue  # Skip boolean values
            
            if kpi_value is None:
                continue
            
            kpi_unit = str(row[unit_col]).strip() if unit_col and pd.notna(row.get(unit_col)) else None
            
            try:
                self.conn.execute("""
                    INSERT INTO kpi_summary (config_id, kpi_name, kpi_value, kpi_unit)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (config_id, kpi_name) DO UPDATE SET 
                        kpi_value = EXCLUDED.kpi_value,
                        kpi_unit = EXCLUDED.kpi_unit
                """, [config_id, kpi_name, kpi_value, kpi_unit])
                imported_count += 1
            except Exception as e:
                pass  # Silently skip individual KPI errors
    
    def get_kpis(self, client_name: str = None, run_name: str = None, 
                 config_name: str = None) -> pd.DataFrame:
        """Get KPIs with optional filters."""
        query = """
            SELECT c.client_name, r.run_name, bc.config_name, 
                   bc.battery_capacity_kwh, kpi.kpi_name, kpi.kpi_value, kpi.kpi_unit
            FROM kpi_summary kpi
            JOIN battery_configs bc ON kpi.config_id = bc.config_id
            JOIN runs r ON bc.run_id = r.run_id
            JOIN clients c ON r.client_id = c.client_id
            WHERE 1=1
        """
        params = []
        
        if client_name:
            query += " AND c.client_name = ?"
            params.append(client_name)
        if run_name:
            query += " AND r.run_name = ?"
            params.append(run_name)
        if config_name:
            query += " AND bc.config_name = ?"
            params.append(config_name)
        
        query += " ORDER BY c.client_name, r.run_name, kpi.kpi_name, bc.battery_capacity_kwh"
        return self.conn.execute(query, params).df()
    
    # =========================================================================
    # Direct CSV Querying (DuckDB Magic!)
    # =========================================================================
    
    def query_timeseries_csv(self, client_name: str, run_name: str, 
                             config_name: str) -> pd.DataFrame:
        """
        Query a timeseries CSV file directly using DuckDB.
        No need to import data - just query the file!
        """
        # Get the file path
        result = self.conn.execute("""
            SELECT bc.timeseries_file_path
            FROM battery_configs bc
            JOIN runs r ON bc.run_id = r.run_id
            JOIN clients c ON r.client_id = c.client_id
            WHERE c.client_name = ? AND r.run_name = ? AND bc.config_name = ?
        """, [client_name, run_name, config_name]).fetchone()
        
        if not result or not result[0]:
            print(f"No timeseries file found for {client_name}/{run_name}/{config_name}")
            return pd.DataFrame()
        
        csv_path = self.data_root / result[0]
        if not csv_path.exists():
            print(f"File not found: {csv_path}")
            return pd.DataFrame()
        
        # Query the CSV directly with DuckDB!
        return self.conn.execute(f"SELECT * FROM read_csv_auto('{csv_path}')").df()
    
    def query_kpi_csv(self, client_name: str, run_name: str, 
                      config_name: str) -> pd.DataFrame:
        """Query a KPI CSV file directly using DuckDB."""
        result = self.conn.execute("""
            SELECT bc.kpi_file_path
            FROM battery_configs bc
            JOIN runs r ON bc.run_id = r.run_id
            JOIN clients c ON r.client_id = c.client_id
            WHERE c.client_name = ? AND r.run_name = ? AND bc.config_name = ?
        """, [client_name, run_name, config_name]).fetchone()
        
        if not result or not result[0]:
            print(f"No KPI file found for {client_name}/{run_name}/{config_name}")
            return pd.DataFrame()
        
        csv_path = self.data_root / result[0]
        if not csv_path.exists():
            print(f"File not found: {csv_path}")
            return pd.DataFrame()
        
        return self.conn.execute(f"SELECT * FROM read_csv_auto('{csv_path}')").df()
    
    def compare_configs(self, client_name: str, run_name: str, 
                        kpi_name: str = None) -> pd.DataFrame:
        """
        Compare all battery configurations within a run.
        
        Args:
            client_name: Client name
            run_name: Run name
            kpi_name: Optional specific KPI to compare
            
        Returns:
            DataFrame with comparison across configs
        """
        query = """
            SELECT bc.config_name, bc.battery_capacity_kwh, bc.battery_power_kw,
                   kpi.kpi_name, kpi.kpi_value, kpi.kpi_unit
            FROM kpi_summary kpi
            JOIN battery_configs bc ON kpi.config_id = bc.config_id
            JOIN runs r ON bc.run_id = r.run_id
            JOIN clients c ON r.client_id = c.client_id
            WHERE c.client_name = ? AND r.run_name = ?
        """
        params = [client_name, run_name]
        
        if kpi_name:
            query += " AND kpi.kpi_name = ?"
            params.append(kpi_name)
        
        query += " ORDER BY kpi.kpi_name, bc.battery_capacity_kwh"
        return self.conn.execute(query, params).df()
    
    # =========================================================================
    # Bulk Import from Existing Folder Structure
    # =========================================================================
    
    def scan_and_import_folder(self, root_path: str = None):
        """
        Scan an existing folder structure and import into database.
        
        Expected structure:
            root/
            ├── ClientName/
            │   ├── RunName/
            │   │   ├── Input/
            │   │   │   └── parameters.json (optional)
            │   │   └── Output/
            │   │       ├── kpi_summary_*.csv / *.xlsx
            │   │       └── flex_timeseries_*.csv
        """
        root = Path(root_path) if root_path else self.data_root
        
        if not root.exists():
            print(f"Root path does not exist: {root}")
            return
        
        for client_folder in root.iterdir():
            if not client_folder.is_dir() or client_folder.name.startswith('.'):
                continue
            
            client_name = client_folder.name
            print(f"\nProcessing client: {client_name}")
            client_id = self.add_client(client_name, create_folder=False)
            
            for run_folder in client_folder.iterdir():
                if not run_folder.is_dir() or run_folder.name.startswith('.'):
                    continue
                
                run_name = run_folder.name
                print(f"  Processing run: {run_name}")
                
                # Load input parameters if available
                input_params = None
                params_file = run_folder / "Input" / "parameters.json"
                if params_file.exists():
                    with open(params_file, 'r') as f:
                        input_params = json.load(f)
                
                # Use the ACTUAL folder path (with spaces) not sanitized
                actual_folder_path = f"{client_folder.name}/{run_folder.name}"
                run_id = self._add_run_with_path(client_name, run_name, 
                                                  actual_folder_path, input_params)
                
                # Scan output files
                output_folder = run_folder / "Output"
                if output_folder.exists():
                    self._import_output_files_direct(client_name, run_name, 
                                                     output_folder, actual_folder_path)
    
    def _extract_config_from_filename(self, filename: str) -> str:
        """
        Extract config name from filename.
        
        Handles patterns like:
        - kpi_summary_20250905_114337_5000kWh.xlsx -> 5000kWh
        - flex_timeseries_outputs_20250905_114337_5000kWh.csv -> 5000kWh
        - kpi_summary_no_battery.csv -> no_battery
        - flex_timeseries_outputs_battery_1.csv -> battery_1
        """
        name = Path(filename).stem
        
        # Check for pattern with timestamp: *_YYYYMMDD_HHMMSS_XXXkWh
        match = re.search(r'_\d{8}_\d{6}_(.+)$', name)
        if match:
            return match.group(1)
        
        # Otherwise extract suffix after known prefixes
        for prefix in ["kpi_summary_", "flex_timeseries_outputs_", "flex_timeseries_"]:
            if name.startswith(prefix):
                return name[len(prefix):]
        
        return name
    
    def _import_output_files(self, client_name: str, run_name: str, 
                             output_folder: Path):
        """Import output files from a run's Output folder."""
        # Find all KPI and timeseries files (support both CSV and Excel)
        kpi_files = list(output_folder.glob("kpi_summary*.csv")) + \
                    list(output_folder.glob("kpi_summary*.xlsx"))
        ts_files = list(output_folder.glob("flex_timeseries*.csv"))
        
        # Extract config names from filenames
        configs = set()
        file_mapping = {}  # config_name -> {kpi: filename, ts: filename}
        
        for f in kpi_files:
            config_name = self._extract_config_from_filename(f.name)
            configs.add(config_name)
            if config_name not in file_mapping:
                file_mapping[config_name] = {}
            file_mapping[config_name]['kpi'] = f.name
        
        for f in ts_files:
            config_name = self._extract_config_from_filename(f.name)
            configs.add(config_name)
            if config_name not in file_mapping:
                file_mapping[config_name] = {}
            file_mapping[config_name]['ts'] = f.name
        
        for config_name in configs:
            print(f"    Processing config: {config_name}")
            
            # Determine if baseline (no_battery, 0_battery, 0kWh, baseline, etc.)
            is_baseline = any(x in config_name.lower() for x in ["no_battery", "0_battery", "0battery", "0kwh", "baseline", "no battery"])
            
            # Parse battery specs from config name if possible
            capacity, power = self._parse_battery_specs(config_name)
            
            # Get files from mapping
            files = file_mapping.get(config_name, {})
            kpi_file = files.get('kpi')
            ts_file = files.get('ts')
            
            config_id = self.add_battery_config(
                client_name=client_name,
                run_name=run_name,
                config_name=config_name,
                is_baseline=is_baseline,
                battery_capacity_kwh=capacity,
                battery_power_kw=power,
                kpi_file=kpi_file,
                timeseries_file=ts_file
            )
            
            # Import KPIs if file exists
            if kpi_file:
                folder_path = self.conn.execute(
                    "SELECT folder_path FROM runs r JOIN clients c ON r.client_id = c.client_id WHERE c.client_name = ? AND r.run_name = ?",
                    [client_name, run_name]
                ).fetchone()[0]
                self.import_kpis_from_csv(config_id, f"{folder_path}/Output/{kpi_file}")
    
    def _import_output_files_direct(self, client_name: str, run_name: str, 
                                    output_folder: Path, actual_folder_path: str):
        """
        Import output files using actual folder paths (with spaces preserved).
        """
        # Find all KPI and timeseries files
        kpi_files = list(output_folder.glob("kpi_summary*.csv")) + \
                    list(output_folder.glob("kpi_summary*.xlsx"))
        ts_files = list(output_folder.glob("flex_timeseries*.csv"))
        
        # Extract config names from filenames
        configs = set()
        file_mapping = {}
        
        for f in kpi_files:
            config_name = self._extract_config_from_filename(f.name)
            configs.add(config_name)
            if config_name not in file_mapping:
                file_mapping[config_name] = {}
            file_mapping[config_name]['kpi'] = f.name
        
        for f in ts_files:
            config_name = self._extract_config_from_filename(f.name)
            configs.add(config_name)
            if config_name not in file_mapping:
                file_mapping[config_name] = {}
            file_mapping[config_name]['ts'] = f.name
        
        for config_name in configs:
            print(f"    Processing config: {config_name}")
            
            # Only exact 0kWh or no_battery is baseline
            config_lower = config_name.lower()
            is_baseline = config_lower in ["0kwh", "0_kwh", "no_battery", "0_battery", "baseline", "no battery"] or \
                         config_lower.startswith("0kwh") or config_lower == "0"
            
            capacity, power = self._parse_battery_specs(config_name)
            
            files = file_mapping.get(config_name, {})
            kpi_file = files.get('kpi')
            ts_file = files.get('ts')
            
            # Get run_id
            run_id = self.get_run_id(client_name, run_name)
            
            # Store the actual file paths (with spaces)
            kpi_file_path = f"{actual_folder_path}/Output/{kpi_file}" if kpi_file else None
            ts_file_path = f"{actual_folder_path}/Output/{ts_file}" if ts_file else None
            
            # Insert config
            try:
                self.conn.execute("""
                    INSERT INTO battery_configs 
                    (run_id, config_name, is_baseline, battery_capacity_kwh, 
                     battery_power_kw, battery_efficiency, other_params,
                     kpi_file_path, timeseries_file_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [run_id, config_name, is_baseline, capacity,
                      power, None, None, kpi_file_path, ts_file_path])
            except (duckdb.ConstraintException, Exception) as e:
                if "unique" in str(e).lower() or "constraint" in str(e).lower():
                    pass
                else:
                    raise
            
            result = self.conn.execute("""
                SELECT config_id FROM battery_configs 
                WHERE run_id = ? AND config_name = ?
            """, [run_id, config_name]).fetchone()
            
            if result and kpi_file:
                self.import_kpis_from_csv(result[0], kpi_file_path)
    
    def _parse_battery_specs(self, config_name: str) -> tuple:
        """Try to extract battery capacity and power from config name."""
        capacity = None
        power = None
        
        # Look for patterns like "100kWh", "50kW", etc.
        cap_match = re.search(r'(\d+(?:\.\d+)?)\s*kWh', config_name, re.IGNORECASE)
        pow_match = re.search(r'(\d+(?:\.\d+)?)\s*kW(?!h)', config_name, re.IGNORECASE)
        
        if cap_match:
            capacity = float(cap_match.group(1))
        if pow_match:
            power = float(pow_match.group(1))
        
        return capacity, power
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize a name for use as a folder name."""
        # Replace spaces and special characters
        sanitized = re.sub(r'[^\w\-]', '_', name)
        return sanitized
    
    def execute(self, query: str, params: list = None) -> pd.DataFrame:
        """Execute a raw SQL query and return results as DataFrame."""
        if params:
            return self.conn.execute(query, params).df()
        return self.conn.execute(query).df()
    
    def summary(self):
        """Print a summary of the database contents."""
        print("\n" + "="*60)
        print("BATTERY SIMULATION DATABASE SUMMARY")
        print("="*60)
        
        clients = self.conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        runs = self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        configs = self.conn.execute("SELECT COUNT(*) FROM battery_configs").fetchone()[0]
        kpis = self.conn.execute("SELECT COUNT(*) FROM kpi_summary").fetchone()[0]
        
        print(f"\nTotal Clients:        {clients}")
        print(f"Total Runs:           {runs}")
        print(f"Battery Configs:      {configs}")
        print(f"KPI Records:          {kpis}")
        
        if clients > 0:
            print("\n" + "-"*60)
            print("HIERARCHY:")
            print("-"*60)
            
            hierarchy = self.conn.execute("""
                SELECT c.client_name, r.run_name, COUNT(bc.config_id) as configs
                FROM clients c
                LEFT JOIN runs r ON c.client_id = r.client_id
                LEFT JOIN battery_configs bc ON r.run_id = bc.run_id
                GROUP BY c.client_name, r.run_name
                ORDER BY c.client_name, r.run_name
            """).fetchall()
            
            current_client = None
            for client, run, configs in hierarchy:
                if client != current_client:
                    print(f"\n📁 {client}")
                    current_client = client
                if run:
                    print(f"   └── 📊 {run} ({configs} battery configs)")
        
        print("\n" + "="*60)


# Convenience function
def get_db(db_path: str = "database/battery_simulations.duckdb") -> BatteryDatabase:
    """Get a database instance."""
    return BatteryDatabase(db_path)


if __name__ == "__main__":
    # Demo usage
    print("Battery Database Demo")
    print("=" * 40)
    
    with BatteryDatabase() as db:
        # Add sample data
        db.add_client("Client_A", "Demo client A")
        db.add_client("Client_B", "Demo client B")
        
        db.add_run(
            client_name="Client_A",
            run_name="2024_Q1_Analysis",
            run_description="Q1 2024 battery sizing study",
            input_parameters={
                "tariff": "TOU",
                "load_profile": "commercial",
                "solar_capacity_kw": 100
            }
        )
        
        db.add_battery_config(
            client_name="Client_A",
            run_name="2024_Q1_Analysis",
            config_name="0_battery",
            is_baseline=True,
            battery_capacity_kwh=0,
            battery_power_kw=0,
            kpi_file="kpi_summary_0_battery.csv",
            timeseries_file="flex_timeseries_0_battery.csv"
        )
        
        db.add_battery_config(
            client_name="Client_A",
            run_name="2024_Q1_Analysis",
            config_name="100kWh_50kW",
            is_baseline=False,
            battery_capacity_kwh=100,
            battery_power_kw=50,
            battery_efficiency=0.92,
            kpi_file="kpi_summary_100kWh_50kW.csv",
            timeseries_file="flex_timeseries_100kWh_50kW.csv"
        )
        
        db.summary()

