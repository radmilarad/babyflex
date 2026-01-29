"""
Data Scraping Module - Quick Reference
=======================================

A collection of scripts to import battery simulation data from Google Drive.
"""

# ============================================================================
# 📁 Files Overview
# ============================================================================

FILES = {
    "__init__.py": "Module exports and package initialization",
    "config.py": "Configuration (paths, patterns, settings)",
    "gdrive_importer.py": "Main Google Drive import logic",
    "folder_scanner.py": "Scan and analyze folder structures",
    "cli.py": "Command-line interface",
    "utils.py": "Helper functions (file parsing, name cleaning)",
    "test_setup.py": "Verify your setup and configuration",
    "example_import.py": "Example usage patterns",
    "README.md": "Full documentation",
    "SETUP.md": "Detailed setup instructions",
    "QUICKSTART.md": "Quick start guide",
}

# ============================================================================
# 🚀 Quick Commands
# ============================================================================

COMMANDS = {
    # Test your setup
    "test": "python3 data_scraping/test_setup.py",
    
    # Preview before importing
    "preview": "python3 -m data_scraping.cli preview --max-clients 10",
    
    # Import all data
    "import_all": "python3 -m data_scraping.cli import-all",
    
    # Import single client
    "import_client": 'python3 -m data_scraping.cli import-client "Georg Jordan GmbH"',
    
    # Scan folder structure
    "scan": "python3 -m data_scraping.cli scan /path/to/folder",
}

# ============================================================================
# 🐍 Python Usage Examples
# ============================================================================

EXAMPLES = """
# Example 1: Simple Import
from data_scraping import GDriveImporter

with GDriveImporter() as importer:
    stats = importer.import_all()
    print(f"Imported {stats['configs_imported']} configurations")

# Example 2: Preview First
from data_scraping import GDriveImporter

importer = GDriveImporter()
importer.preview(max_clients=5)
importer.close()

# Example 3: Import Specific Client
from data_scraping import GDriveImporter

with GDriveImporter() as importer:
    success = importer.import_client("Benecke-Kaliko AG")
    if success:
        print("✅ Import successful")

# Example 4: Custom Path
from data_scraping import GDriveImporter

importer = GDriveImporter(
    db_path="database/battery_simulations.duckdb",
    gdrive_base="/custom/path/to/flex_cases"
)
importer.import_all()
importer.close()

# Example 5: Scan Folder
from data_scraping import scan_folder_structure

info = scan_folder_structure("/path/to/folder")
print(f"Found {info['total_files']} files")
"""

# ============================================================================
# ⚙️ Configuration
# ============================================================================

CONFIG_INFO = """
Edit data_scraping/config.py to customize:

GDRIVE_CONFIG = {
    "base_path": "/path/to/google/drive",
    "flex_cases_folder": "38_Flex – Business Dev/01_Flex_Cases",
    "flex_subfolder": "02_Flex Offer Files",
    "skip_patterns": ["00_", "Archive", "Template"],
    "client_name_suffixes": [" (F)", " (Flex)"],
}

IMPORT_SETTINGS = {
    "kpi_patterns": ["kpi_summary*.csv", "kpi_summary*.xlsx"],
    "timeseries_patterns": ["flex_timeseries*.csv"],
    "config_patterns": ["load_config*.yml", "parameters.json"],
}
"""

# ============================================================================
# 🔧 Installation
# ============================================================================

INSTALL = """
# Install required dependencies
pip install pyyaml openpyxl

# Or install all at once
pip install pandas duckdb pyyaml openpyxl tabulate
"""

# ============================================================================
# 📊 What Gets Imported
# ============================================================================

IMPORT_FLOW = """
Google Drive Structure:
    Client Name (F)/
    └── 02_Flex Offer Files/
        └── Run 1/
            ├── Input/
            │   └── load_config*.yml
            └── Output/
                ├── kpi_summary_*.csv
                └── flex_timeseries_*.csv

Database Tables:
    clients          → Client metadata
    runs             → Run metadata with input parameters
    battery_configs  → Each battery configuration
    kpi_summary      → All KPIs for each config
"""


if __name__ == "__main__":
    print(__doc__)
    print("\n" + "="*70)
    print("AVAILABLE FILES")
    print("="*70)
    for filename, description in FILES.items():
        print(f"  {filename:25s} {description}")
    
    print("\n" + "="*70)
    print("QUICK COMMANDS")
    print("="*70)
    for name, cmd in COMMANDS.items():
        print(f"\n{name}:")
        print(f"  {cmd}")
    
    print("\n" + "="*70)
    print("PYTHON EXAMPLES")
    print("="*70)
    print(EXAMPLES)
    
    print("\n" + "="*70)
    print("INSTALLATION")
    print("="*70)
    print(INSTALL)

