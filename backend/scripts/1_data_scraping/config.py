"""
Configuration for Data Scraping
================================

Paths and settings for importing data from Google Drive and other sources.
"""

import os
from pathlib import Path
from typing import Optional


# ============================================================================
# Google Drive Configuration
# ============================================================================

GDRIVE_CONFIG = {
    # Base path to the locally mirrored Google Drive
    "base_path": (
        "/Users/jonasgleissner/Library/CloudStorage/"
        "GoogleDrive-jonas.gleissner@trawa.de/"
        ".shortcut-targets-by-id/1EYADLyWM0Pn5DptM4a9n5frnyGoAnzdp/17_Tech"
    ),
    
    # Path to flex cases folder (relative to base_path)
    "flex_cases_folder": "38_Flex – Business Dev/01_Flex_Cases",
    
    # Subfolder within each client containing simulation runs
    "flex_subfolder": "02_Flex Offer Files",
    
    # Patterns to skip when scanning client folders
    "skip_patterns": [
        "00_",           # Utility folders
        "01_Template",   # Templates
        "02_Template",
        "03_",           # Process folders
        "04_",
        "05_",
        "06_",
        "07_",
        "Archive",
        "Cheatsheet",
        ".zip",
        ".xlsx",
        ".gsheet",
        ".gdoc",
        ".gslides",
        ".py",
        ".txt",
    ],
    
    # Suffixes to strip from client names
    "client_name_suffixes": [
        " (F)",
        " (Flex)",
        " - Batterie",
    ],
}


def get_gdrive_path(subpath: str = None) -> Path:
    """
    Get the full path to a Google Drive location.
    
    Args:
        subpath: Optional subpath relative to base
        
    Returns:
        Full path to the location
        
    Example:
        >>> get_gdrive_path("38_Flex – Business Dev/01_Flex_Cases")
        Path('/Users/.../17_Tech/38_Flex – Business Dev/01_Flex_Cases')
    """
    base = Path(os.getenv("GDRIVE_BASE_PATH", GDRIVE_CONFIG["base_path"]))
    
    if subpath:
        return base / subpath
    return base


def get_flex_cases_path() -> Path:
    """Get the full path to the flex cases folder."""
    return get_gdrive_path(GDRIVE_CONFIG["flex_cases_folder"])


# ============================================================================
# Import Settings
# ============================================================================

IMPORT_SETTINGS = {
    # File patterns to look for
    "kpi_patterns": ["kpi_summary*.csv", "kpi_summary*.xlsx"],
    "timeseries_patterns": ["flex_timeseries*.csv"],
    "config_patterns": ["load_config*.yml", "load_config*.yaml", "parameters.json"],
    
    # How to detect baseline configs
    "baseline_names": [
        "0kwh", "0_kwh", "no_battery", "0_battery", 
        "baseline", "no battery", "0"
    ],
}
