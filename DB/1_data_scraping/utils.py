"""
Utility Functions for Data Scraping
=====================================

Helper functions for file parsing, validation, and data transformation.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import pandas as pd


def validate_kpi_file(file_path: str, required_columns: int = 2) -> Tuple[bool, str]:
    """
    Validate a KPI summary file.
    
    Args:
        file_path: Path to the KPI file
        required_columns: Minimum number of columns required
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(file_path)
    
    if not path.exists():
        return False, f"File not found: {file_path}"
    
    try:
        if path.suffix in ['.xlsx', '.xls']:
            df = pd.read_excel(path)
        else:
            df = pd.read_csv(path)
    except Exception as e:
        return False, f"Could not read file: {e}"
    
    if len(df.columns) < required_columns:
        return False, f"File has {len(df.columns)} columns, need at least {required_columns}"
    
    if len(df) == 0:
        return False, "File is empty"
    
    return True, ""


def validate_timeseries_file(file_path: str, 
                             min_rows: int = 100) -> Tuple[bool, str]:
    """
    Validate a timeseries file.
    
    Args:
        file_path: Path to the timeseries file
        min_rows: Minimum number of rows required
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(file_path)
    
    if not path.exists():
        return False, f"File not found: {file_path}"
    
    try:
        # Read just the header and first few rows to check structure
        df = pd.read_csv(path, nrows=min_rows + 10)
    except Exception as e:
        return False, f"Could not read file: {e}"
    
    if len(df) < min_rows:
        return False, f"File has {len(df)} rows, need at least {min_rows}"
    
    # Check for timestamp column
    timestamp_cols = [c for c in df.columns if 'time' in c.lower() or 'date' in c.lower()]
    if not timestamp_cols:
        return False, "No timestamp column found"
    
    return True, ""


def parse_battery_config_from_yaml(yaml_content: Dict) -> Dict[str, Any]:
    """
    Parse battery configuration from YAML content.
    
    Args:
        yaml_content: Parsed YAML dictionary
        
    Returns:
        Dictionary with extracted battery parameters
    """
    config = {}
    
    # Common keys to look for
    key_mappings = {
        "battery_capacity_kwh": ["battery_capacity", "capacity_kwh", "battery_kwh", "capacity"],
        "battery_power_kw": ["battery_power", "power_kw", "battery_kw", "power"],
        "battery_efficiency": ["efficiency", "round_trip_efficiency", "rte"],
    }
    
    for target_key, source_keys in key_mappings.items():
        for source_key in source_keys:
            if source_key in yaml_content:
                config[target_key] = yaml_content[source_key]
                break
    
    return config


def clean_kpi_name(name: str) -> str:
    """
    Standardize KPI names for consistency.
    
    Args:
        name: Original KPI name
        
    Returns:
        Cleaned KPI name
    """
    # Convert to lowercase and replace spaces with underscores
    cleaned = name.lower().strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    cleaned = re.sub(r'[^\w_]', '', cleaned)
    
    # Common standardizations
    replacements = {
        "peak_shaving": "peak_shaving_benefit",
        "energy_optimization": "energy_procurement_optimization",
        "trading": "trading_revenue",
    }
    
    for old, new in replacements.items():
        if cleaned == old:
            cleaned = new
            break
    
    return cleaned


def extract_date_from_folder_name(folder_name: str) -> Optional[datetime]:
    """
    Try to extract a date from a folder name.
    
    Args:
        folder_name: Name of the folder
        
    Returns:
        datetime if found, None otherwise
    """
    # Common patterns
    patterns = [
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # DD.MM.YYYY
        r'(\d{4})-(\d{2})-(\d{2})',         # YYYY-MM-DD
        r'(\d{8})',                          # YYYYMMDD
    ]
    
    for pattern in patterns:
        match = re.search(pattern, folder_name)
        if match:
            try:
                groups = match.groups()
                if len(groups) == 3:
                    if len(groups[2]) == 4:  # DD.MM.YYYY
                        return datetime(int(groups[2]), int(groups[1]), int(groups[0]))
                    else:  # YYYY-MM-DD
                        return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
                elif len(groups) == 1 and len(groups[0]) == 8:  # YYYYMMDD
                    return datetime.strptime(groups[0], '%Y%m%d')
            except ValueError:
                continue
    
    return None


def get_file_size_mb(file_path: str) -> float:
    """Get file size in megabytes."""
    path = Path(file_path)
    if path.exists():
        return path.stat().st_size / (1024 * 1024)
    return 0.0


def find_output_files(output_folder: Path) -> Dict[str, List[Path]]:
    """
    Find and categorize output files in a folder.
    
    Args:
        output_folder: Path to the Output folder
        
    Returns:
        Dictionary with 'kpi' and 'timeseries' file lists
    """
    files = {
        "kpi": [],
        "timeseries": [],
        "other": [],
    }
    
    if not output_folder.exists():
        return files
    
    for f in output_folder.iterdir():
        if not f.is_file():
            continue
        
        name_lower = f.name.lower()
        
        if 'kpi' in name_lower and f.suffix in ['.csv', '.xlsx', '.xls']:
            files["kpi"].append(f)
        elif 'timeseries' in name_lower and f.suffix == '.csv':
            files["timeseries"].append(f)
        elif f.suffix in ['.csv', '.xlsx', '.xls']:
            files["other"].append(f)
    
    return files


def generate_import_report(stats: Dict) -> str:
    """
    Generate a formatted import report.
    
    Args:
        stats: Statistics dictionary from importer
        
    Returns:
        Formatted report string
    """
    lines = [
        "=" * 60,
        "IMPORT REPORT",
        "=" * 60,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Summary:",
        f"  Clients found:     {stats.get('clients_found', 0)}",
        f"  Clients imported:  {stats.get('clients_imported', 0)}",
        f"  Runs imported:     {stats.get('runs_imported', 0)}",
        f"  Configs imported:  {stats.get('configs_imported', 0)}",
        f"  KPIs imported:     {stats.get('kpis_imported', 0)}",
    ]
    
    errors = stats.get('errors', [])
    if errors:
        lines.extend([
            "",
            f"Errors ({len(errors)}):",
        ])
        for error in errors[:20]:
            lines.append(f"  - {error}")
        if len(errors) > 20:
            lines.append(f"  ... and {len(errors) - 20} more")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)

