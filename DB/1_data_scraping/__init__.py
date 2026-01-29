"""
Data Scraping Module
====================

Tools for importing battery simulation data from various sources,
including Google Drive mirrored folders.

Usage:
    from data_scraping import GDriveImporter, scan_folder_structure
    
    # Import from Google Drive
    importer = GDriveImporter()
    importer.import_all()
    
    # Scan a folder to preview structure
    from data_scraping import scan_folder_structure
    scan_folder_structure("/path/to/folder")
"""

from .config import GDRIVE_CONFIG, get_gdrive_path
from .gdrive_importer import GDriveImporter
from .folder_scanner import scan_folder_structure, find_flex_cases

__all__ = [
    "GDriveImporter",
    "scan_folder_structure", 
    "find_flex_cases",
    "GDRIVE_CONFIG",
    "get_gdrive_path",
]
