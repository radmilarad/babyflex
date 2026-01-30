# Data Scraping Quick Start Guide

## 🎯 What This Does

Automatically imports battery simulation data from your Google Drive into the DuckDB database.

## 📁 Folder Structure

The data_scraping module includes:

```
data_scraping/
├── __init__.py              # Module exports
├── config.py                # Configuration (paths, patterns)
├── gdrive_importer.py       # Main import logic
├── folder_scanner.py        # Folder structure analysis
├── cli.py                   # Command-line interface
├── utils.py                 # Helper functions
├── example_import.py        # Example usage scripts
├── test_setup.py            # Test your configuration
├── README.md                # Full documentation
├── SETUP.md                 # Setup instructions
└── QUICKSTART.md            # This file
```

## 🚀 Quick Commands

### 1. Test Your Setup

```bash
python data_scraping/test_setup.py
```

This checks:
- ✅ Google Drive path exists
- ✅ Database is accessible
- ✅ Flex cases folder is found
- ✅ Client folders are detected

### 2. Preview Before Importing

```bash
python -m data_scraping.cli preview --max-clients 10
```

Shows what will be imported without actually importing.

### 3. Import Everything

```bash
python -m data_scraping.cli import-all
```

Imports all clients, runs, and configurations from Google Drive.

### 4. Import a Single Client

```bash
python -m data_scraping.cli import-client "Georg Jordan GmbH"
```

## 📝 Python Usage

### Simple Import

```python
from data_scraping import GDriveImporter

# Import everything
with GDriveImporter() as importer:
    stats = importer.import_all()
    print(f"Imported {stats['configs_imported']} configurations")
```

### Preview First

```python
from data_scraping import GDriveImporter

importer = GDriveImporter()
importer.preview(max_clients=5)  # See what's available
importer.close()
```

### Import Specific Client

```python
from data_scraping import GDriveImporter

with GDriveImporter() as importer:
    success = importer.import_client("Benecke-Kaliko AG")
```

## ⚙️ Configuration

The default configuration in `config.py` points to:

```python
/Users/jonasgleissner/Library/CloudStorage/GoogleDrive-jonas.gleissner@trawa.de/
.shortcut-targets-by-id/1EYADLyWM0Pn5DptM4a9n5frnyGoAnzdp/17_Tech/
38_Flex – Business Dev/01_Flex_Cases
```

### Custom Path

Override with environment variable:

```bash
export GDRIVE_BASE_PATH="/custom/path/to/gdrive"
python -m data_scraping.cli import-all
```

Or in Python:

```python
from data_scraping import GDriveImporter

importer = GDriveImporter(gdrive_base="/custom/path")
importer.import_all()
```

## 🎨 What Gets Imported

For each client in Google Drive:

```
Client Name (F)/
└── 02_Flex Offer Files/
    └── Run 1/
        ├── Input/
        │   └── load_config*.yml          → input_parameters
        └── Output/
            ├── kpi_summary_*.csv         → kpi_summary table
            └── flex_timeseries_*.csv     → file paths stored
```

**Result in Database:**
- `clients` table: Client name
- `runs` table: Run metadata
- `battery_configs` table: Each configuration (0kWh, 1000kWh, etc.)
- `kpi_summary` table: All KPIs for each config

## 📊 View Results

After importing:

```bash
python cli.py summary
python cli.py list clients
python cli.py query "SELECT * FROM v_full_hierarchy LIMIT 10"
```

Or in Python:

```python
from battery_db import BatteryDatabase

db = BatteryDatabase()
print(db.get_clients())
print(db.get_runs())
db.summary()
```

## 🐛 Troubleshooting

### "Path not found"
- Ensure Google Drive is synced
- Check path in `config.py` matches your system
- Run `python data_scraping/test_setup.py`

### "No clients found"
- Check `skip_patterns` in `config.py`
- Verify folders contain `02_Flex Offer Files` subfolder
- Ensure Output folders have CSV files

### Duplicates
- Safe to re-run - duplicates are automatically handled
- Existing data is skipped or updated

## 💡 Tips

1. **Always preview first** to see what will be imported
2. **Start with one client** to test: `import-client "ClientName"`
3. **Check the database** after import: `python cli.py summary`
4. **Monitor progress** - the importer shows detailed progress

## 📚 Next Steps

- Read `README.md` for full documentation
- Check `SETUP.md` for detailed setup
- See `example_import.py` for more usage examples
- Explore `folder_scanner.py` for custom scanning

## 🔗 Integration

The importer integrates with your existing CLI:

```bash
# Import from Google Drive
python -m data_scraping.cli import-all

# Then use your main CLI
python cli.py summary
python cli.py extract-features
python cli.py train peak_shaving_benefit
```

