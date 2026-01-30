"""
Google Drive Importer
=====================

Import battery simulation data from locally mirrored Google Drive folders.

Usage:
    from data_scraping import GDriveImporter
    
    importer = GDriveImporter()
    importer.import_all()
    
    # Or preview first
    importer.preview()
"""

import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import pandas as pd

from battery_db import BatteryDatabase
from .config import GDRIVE_CONFIG, IMPORT_SETTINGS, get_flex_cases_path


class GDriveImporter:
    """Import battery simulation data from Google Drive."""
    
    def __init__(self, 
                 db_path: str = "database/battery_simulations.duckdb",
                 gdrive_base: str = None):
        """
        Initialize the importer.
        
        Args:
            db_path: Path to DuckDB database
            gdrive_base: Override default Google Drive base path
        """
        self.db = BatteryDatabase(db_path)
        self.gdrive_base = Path(gdrive_base) if gdrive_base else get_flex_cases_path()
        self.config = GDRIVE_CONFIG
        self.import_settings = IMPORT_SETTINGS
        
        self.stats = {
            "clients_found": 0,
            "clients_imported": 0,
            "runs_found": 0,
            "runs_imported": 0,
            "configs_imported": 0,
            "kpis_imported": 0,
            "errors": [],
        }
    
    def preview(self, max_clients: int = 10) -> Dict:
        """
        Preview what would be imported without actually importing.
        
        Args:
            max_clients: Maximum clients to preview
            
        Returns:
            Dictionary with preview statistics
        """
        print(f"\n{'='*70}")
        print(f"PREVIEW: Scanning {self.gdrive_base}")
        print(f"{'='*70}\n")
        
        preview_data = []
        count = 0
        
        for client_folder in sorted(self.gdrive_base.iterdir()):
            if count >= max_clients:
                break
                
            if not self._should_process_folder(client_folder):
                continue
            
            client_name = self._clean_client_name(client_folder.name)
            flex_path = client_folder / self.config["flex_subfolder"]
            
            if not flex_path.exists():
                continue
            
            runs = self._find_runs(flex_path)
            if runs:
                preview_data.append({
                    "client": client_name,
                    "folder": client_folder.name,
                    "runs": len(runs),
                    "run_names": [r.name for r in runs]
                })
                count += 1
        
        # Print preview
        for item in preview_data:
            print(f"📁 {item['client']}")
            print(f"   Folder: {item['folder']}")
            print(f"   Runs: {item['runs']}")
            for run in item['run_names']:
                print(f"      └── {run}")
            print()
        
        print(f"{'='*70}")
        print(f"Total clients to import: {len(preview_data)}")
        print(f"{'='*70}\n")
        
        return preview_data
    
    def import_all(self, dry_run: bool = False) -> Dict:
        """
        Import all battery simulation data from Google Drive.
        
        Args:
            dry_run: If True, preview only without importing
            
        Returns:
            Dictionary with import statistics
        """
        if dry_run:
            return self.preview()
        
        print(f"\n{'='*70}")
        print(f"IMPORTING FROM: {self.gdrive_base}")
        print(f"{'='*70}\n")
        
        if not self.gdrive_base.exists():
            print(f"❌ Path not found: {self.gdrive_base}")
            return self.stats
        
        for client_folder in sorted(self.gdrive_base.iterdir()):
            if not self._should_process_folder(client_folder):
                continue
            
            self.stats["clients_found"] += 1
            
            try:
                self._import_client(client_folder)
            except Exception as e:
                error_msg = f"Error processing {client_folder.name}: {e}"
                print(f"❌ {error_msg}")
                self.stats["errors"].append(error_msg)
        
        self._print_summary()
        return self.stats
    
    def import_client(self, client_name: str) -> bool:
        """
        Import a specific client by name.
        
        Args:
            client_name: Name of the client folder
            
        Returns:
            True if successful, False otherwise
        """
        for client_folder in self.gdrive_base.iterdir():
            if client_folder.name == client_name or \
               self._clean_client_name(client_folder.name) == client_name:
                try:
                    self._import_client(client_folder)
                    return True
                except Exception as e:
                    print(f"❌ Error importing {client_name}: {e}")
                    return False
        
        print(f"❌ Client folder not found: {client_name}")
        return False
    
    def _should_process_folder(self, folder: Path) -> bool:
        """Check if a folder should be processed."""
        if not folder.is_dir() or folder.name.startswith('.'):
            return False
        
        # Skip folders matching patterns
        for pattern in self.config["skip_patterns"]:
            if pattern in folder.name:
                return False
        
        return True
    
    def _clean_client_name(self, folder_name: str) -> str:
        """Clean client name by removing suffixes."""
        name = folder_name
        for suffix in self.config["client_name_suffixes"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.strip()
    
    def _find_runs(self, flex_path: Path) -> List[Path]:
        """Find all valid run folders."""
        if not flex_path.exists():
            return []
        
        runs = []
        for run_folder in flex_path.iterdir():
            if not run_folder.is_dir() or run_folder.name.startswith('.'):
                continue
            
            output_folder = run_folder / "Output"
            if output_folder.exists():
                # Check for actual output files
                has_files = any(output_folder.glob(pattern) 
                              for pattern in self.import_settings["kpi_patterns"] + 
                                           self.import_settings["timeseries_patterns"])
                if has_files:
                    runs.append(run_folder)
        
        return runs
    
    def _import_client(self, client_folder: Path):
        """Import all data for a client."""
        client_name = self._clean_client_name(client_folder.name)
        flex_path = client_folder / self.config["flex_subfolder"]
        
        if not flex_path.exists():
            return
        
        runs = self._find_runs(flex_path)
        if not runs:
            return
        
        print(f"\n📁 Processing client: {client_name}")
        self.db.add_client(client_name, create_folder=False)
        self.stats["clients_imported"] += 1
        
        for run_folder in runs:
            self.stats["runs_found"] += 1
            self._import_run(client_name, run_folder)
    
    def _import_run(self, client_name: str, run_folder: Path):
        """Import a single run."""
        run_name = run_folder.name
        print(f"   └── 📊 Processing run: {run_name}")
        
        # Load input parameters
        input_params = self._load_input_params(run_folder / "Input")
        
        # Add run with absolute path for file access
        run_id = self._add_run_to_db(client_name, run_name, str(run_folder), input_params)
        
        if not run_id:
            return
        
        self.stats["runs_imported"] += 1
        
        # Import output files
        config_count = self._import_output_files(client_name, run_name, run_id, 
                                                 run_folder / "Output")
        self.stats["configs_imported"] += config_count
    
    def _load_input_params(self, input_folder: Path) -> Optional[Dict]:
        """Load input parameters from various file formats."""
        if not input_folder.exists():
            return None
        
        # Try JSON files first
        for filename in ["parameters.json", "config.json", "params.json"]:
            params_file = input_folder / filename
            if params_file.exists():
                try:
                    with open(params_file, 'r') as f:
                        return json.load(f)
                except:
                    pass
        
        # Try YAML config files
        yaml_files = list(input_folder.glob("load_config*.yml")) + \
                     list(input_folder.glob("load_config*.yaml"))
        if yaml_files:
            try:
                import yaml
                with open(yaml_files[0], 'r') as f:
                    return yaml.safe_load(f)
            except:
                pass
        
        return None
    
    def _add_run_to_db(self, client_name: str, run_name: str, 
                       folder_path: str, input_params: Optional[Dict]) -> Optional[int]:
        """Add a run to the database."""
        client_id = self.db.get_client_id(client_name)
        if not client_id:
            client_id = self.db.add_client(client_name, create_folder=False)
        
        params_json = json.dumps(input_params) if input_params else None
        
        try:
            self.db.conn.execute("""
                INSERT INTO runs (client_id, run_name, run_description, run_date, 
                                  input_parameters, folder_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [client_id, run_name, None, None, params_json, folder_path])
        except Exception as e:
            if "unique" not in str(e).lower() and "constraint" not in str(e).lower():
                raise
        
        return self.db.get_run_id(client_name, run_name)
    
    def _import_output_files(self, client_name: str, run_name: str, 
                            run_id: int, output_folder: Path) -> int:
        """Import output files for a run. Returns count of configs imported."""
        if not output_folder.exists():
            return 0
        
        # Find all files
        kpi_files = []
        ts_files = []
        
        for pattern in self.import_settings["kpi_patterns"]:
            kpi_files.extend(output_folder.glob(pattern))
        
        for pattern in self.import_settings["timeseries_patterns"]:
            ts_files.extend(output_folder.glob(pattern))
        
        # Map files to configs
        configs = set()
        file_mapping = {}
        
        for f in kpi_files:
            config_name = self._extract_config_name(f.name)
            configs.add(config_name)
            file_mapping.setdefault(config_name, {})['kpi'] = str(f)
        
        for f in ts_files:
            config_name = self._extract_config_name(f.name)
            configs.add(config_name)
            file_mapping.setdefault(config_name, {})['ts'] = str(f)
        
        # Import each config
        imported = 0
        for config_name in sorted(configs):
            if self._import_config(run_id, config_name, file_mapping.get(config_name, {})):
                imported += 1
        
        return imported
    
    def _extract_config_name(self, filename: str) -> str:
        """Extract config name from filename."""
        import re
        
        name = Path(filename).stem
        
        # Pattern: *_YYYYMMDD_HHMMSS_XXXkWh
        match = re.search(r'_\d{8}_\d{6}_(.+)$', name)
        if match:
            return match.group(1)
        
        # Remove known prefixes
        for prefix in ["kpi_summary_", "flex_timeseries_outputs_", "flex_timeseries_"]:
            if name.startswith(prefix):
                return name[len(prefix):]
        
        return name
    
    def _is_baseline(self, config_name: str) -> bool:
        """Determine if a config is a baseline (no battery)."""
        return config_name.lower() in self.import_settings["baseline_names"]
    
    def _parse_battery_specs(self, config_name: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract battery capacity and power from config name."""
        import re
        
        capacity = None
        power = None
        
        cap_match = re.search(r'(\d+(?:\.\d+)?)\s*kWh', config_name, re.IGNORECASE)
        pow_match = re.search(r'(\d+(?:\.\d+)?)\s*kW(?!h)', config_name, re.IGNORECASE)
        
        if cap_match:
            capacity = float(cap_match.group(1))
        if pow_match:
            power = float(pow_match.group(1))
        
        return capacity, power
    
    def _import_config(self, run_id: int, config_name: str, files: Dict) -> bool:
        """Import a single battery configuration."""
        is_baseline = self._is_baseline(config_name)
        capacity, power = self._parse_battery_specs(config_name)
        
        kpi_path = files.get('kpi')
        ts_path = files.get('ts')
        
        try:
            self.db.conn.execute("""
                INSERT INTO battery_configs 
                (run_id, config_name, is_baseline, battery_capacity_kwh, 
                 battery_power_kw, kpi_file_path, timeseries_file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [run_id, config_name, is_baseline, capacity, power, kpi_path, ts_path])
            
            # Import KPIs
            if kpi_path:
                result = self.db.conn.execute(
                    "SELECT config_id FROM battery_configs WHERE run_id = ? AND config_name = ?",
                    [run_id, config_name]
                ).fetchone()
                
                if result:
                    kpi_count = self._import_kpis(result[0], kpi_path)
                    self.stats["kpis_imported"] += kpi_count
            
            return True
            
        except Exception as e:
            if "unique" not in str(e).lower():
                print(f"      Warning: {e}")
            return False
    
    def _import_kpis(self, config_id: int, kpi_file_path: str) -> int:
        """Import KPIs from a file. Returns count of KPIs imported."""
        path = Path(kpi_file_path)
        if not path.exists():
            return 0
        
        try:
            if str(path).endswith(('.xlsx', '.xls')):
                df = pd.read_excel(path)
            else:
                df = pd.read_csv(path)
        except Exception:
            return 0
        
        if len(df.columns) < 2:
            return 0
        
        # Detect columns
        name_col = df.columns[0]
        value_col = df.columns[1]
        
        for col in df.columns:
            if 'name' in col.lower() or 'kpi' in col.lower():
                name_col = col
            elif 'value' in col.lower():
                value_col = col
        
        unit_col = next((c for c in df.columns if 'unit' in c.lower()), None)
        
        imported = 0
        for _, row in df.iterrows():
            kpi_name = str(row[name_col]).strip()
            raw_value = row[value_col]
            
            if not kpi_name or kpi_name == 'nan':
                continue
            
            # Convert to float
            kpi_value = None
            if pd.notna(raw_value):
                if isinstance(raw_value, (int, float)):
                    kpi_value = float(raw_value)
                elif isinstance(raw_value, str):
                    try:
                        kpi_value = float(raw_value.strip())
                    except ValueError:
                        continue
            
            if kpi_value is None:
                continue
            
            kpi_unit = str(row[unit_col]).strip() if unit_col and pd.notna(row.get(unit_col)) else None
            
            try:
                self.db.conn.execute("""
                    INSERT INTO kpi_summary (config_id, kpi_name, kpi_value, kpi_unit)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (config_id, kpi_name) DO UPDATE SET 
                        kpi_value = EXCLUDED.kpi_value,
                        kpi_unit = EXCLUDED.kpi_unit
                """, [config_id, kpi_name, kpi_value, kpi_unit])
                imported += 1
            except:
                pass
        
        return imported
    
    def _print_summary(self):
        """Print import summary."""
        print(f"\n{'='*70}")
        print("IMPORT SUMMARY")
        print(f"{'='*70}")
        print(f"Clients found:      {self.stats['clients_found']}")
        print(f"Clients imported:   {self.stats['clients_imported']}")
        print(f"Runs found:         {self.stats['runs_found']}")
        print(f"Runs imported:      {self.stats['runs_imported']}")
        print(f"Configs imported:   {self.stats['configs_imported']}")
        print(f"KPIs imported:      {self.stats['kpis_imported']}")
        
        if self.stats['errors']:
            print(f"\nErrors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:10]:  # Show first 10
                print(f"  ❌ {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")
        
        print(f"{'='*70}\n")
    
    def close(self):
        """Close database connection."""
        self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
