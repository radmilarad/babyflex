# Data Scraping Module

Tools for importing battery simulation data from various sources into the DuckDB database.

## Features

- **Google Drive Import**: Automatically import from locally mirrored Google Drive folders
- **Folder Scanner**: Preview and analyze folder structures before importing
- **Flexible Configuration**: Easy customization of paths and patterns

## Quick Start

### 1. Preview What Will Be Imported

```python
from data_scraping import GDriveImporter

importer = GDriveImporter()
importer.preview(max_clients=10)  # Preview first 10 clients
```

### 2. Import All Data

```python
from data_scraping import GDriveImporter

with GDriveImporter() as importer:
    stats = importer.import_all()
    print(f"Imported {stats['configs_imported']} configurations")
```

### 3. Import a Specific Client

```python
from data_scraping import GDriveImporter

importer = GDriveImporter()
success = importer.import_client("Georg Jordan GmbH")
importer.close()
```

## Command-Line Usage

### Import from Google Drive

```bash
# Preview what will be imported
python -m data_scraping.cli preview

# Import all data
python -m data_scraping.cli import-all

# Import specific client
python -m data_scraping.cli import-client "Georg Jordan GmbH"
```

### Scan Folder Structure

```bash
# Scan and report on folder structure
python -m data_scraping.folder_scanner /path/to/folder

# Or use Python
python -c "from data_scraping import scan_folder_structure; scan_folder_structure('/path/to/folder')"
```

## Configuration

Edit `data_scraping/config.py` to customize:

- **Google Drive paths**: Change base path for different machines
- **Folder patterns**: Skip certain folders during import
- **File patterns**: Customize which files to import
- **Client name cleaning**: Remove suffixes like "(F)" or "(Flex)"

### Environment Variables

You can override the default Google Drive path:

```bash
export GDRIVE_BASE_PATH="/path/to/your/google/drive"
```

## Folder Structure Expected

```
Google Drive Root/
├── Client Name (F)/
│   ├── 01_Daten vom Kunden/
│   ├── 02_Flex Offer Files/
│   │   ├── Run 1/
│   │   │   ├── Input/
│   │   │   │   └── load_config*.yml
│   │   │   └── Output/
│   │   │       ├── kpi_summary_*.csv
│   │   │       └── flex_timeseries_*.csv
│   │   └── Run 2/
│   │       └── ...
│   └── ...
└── Another Client/
    └── ...
```

## API Reference

### GDriveImporter

```python
class GDriveImporter:
    def __init__(self, db_path: str, gdrive_base: str = None)
    def preview(self, max_clients: int = 10) -> Dict
    def import_all(self, dry_run: bool = False) -> Dict
    def import_client(self, client_name: str) -> bool
```

### Folder Scanner

```python
def scan_folder_structure(root_path: str, max_depth: int = 3) -> Dict
def find_flex_cases(root_path: str, flex_subfolder: str) -> List[Dict]
def preview_import(root_path: str, flex_subfolder: str, max_clients: int)
```

## Import Statistics

After import, you'll get statistics:

```python
{
    "clients_found": 150,
    "clients_imported": 142,
    "runs_found": 380,
    "runs_imported": 375,
    "configs_imported": 1250,
    "kpis_imported": 15000,
    "errors": []
}
```

## Troubleshooting

### Path Not Found

If you get "Path not found", check:
1. Google Drive is synced and mounted
2. Path in `config.py` matches your system
3. You have read permissions

### No Data Imported

If nothing imports:
1. Check folder structure matches expected format
2. Verify `02_Flex Offer Files` subfolder exists
3. Ensure Output folders contain CSV/Excel files
4. Check skip patterns in `config.py`

### Duplicate Errors

The importer safely handles duplicates - if data already exists, it will skip and continue.

## Examples

### Custom Google Drive Path

```python
from data_scraping import GDriveImporter

importer = GDriveImporter(
    db_path="database/my_database.duckdb",
    gdrive_base="/custom/path/to/flex/cases"
)
importer.import_all()
```

### Scan Before Importing

```python
from data_scraping import preview_import

preview_import(
    root_path="/path/to/google/drive/flex_cases",
    flex_subfolder="02_Flex Offer Files",
    max_clients=20
)
```
