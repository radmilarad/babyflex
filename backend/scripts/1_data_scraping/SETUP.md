# Data Scraping Module - Complete Setup

## ✅ Created Files

The `data_scraping/` folder has been successfully created with all necessary scripts:

```
data_scraping/
├── __init__.py              # Module exports and public API
├── config.py                # Configuration (paths, patterns, settings)
├── gdrive_importer.py       # Main Google Drive import logic
├── folder_scanner.py        # Folder structure analysis tools
├── cli.py                   # Command-line interface
├── utils.py                 # Helper functions (validation, parsing)
├── example_import.py        # Complete usage example
└── README.md                # Full documentation
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The following dependency was added:
- `pyyaml>=6.0.0` (for reading YAML config files)

### 2. Check Your Google Drive Path

```bash
python -m data_scraping.cli show-path
```

This shows the configured path and verifies it exists.

### 3. Preview What Will Be Imported

```bash
python -m data_scraping.cli preview --max-clients 10
```

This scans your Google Drive and shows what would be imported.

### 4. Import Data

```bash
# Import everything
python -m data_scraping.cli import-all

# Or import a specific client
python -m data_scraping.cli import-client "Georg Jordan GmbH"
```

## 📊 Python API Usage

### Basic Import

```python
from data_scraping import GDriveImporter

# Create importer and preview
importer = GDriveImporter()
importer.preview(max_clients=5)

# Import all data
stats = importer.import_all()
print(f"Imported {stats['configs_imported']} configurations")

importer.close()
```

### Using Context Manager

```python
from data_scraping import GDriveImporter

with GDriveImporter() as importer:
    stats = importer.import_all()
```

### Scan Folder Structure

```python
from data_scraping import scan_folder_structure, preview_import

# Detailed scan
scan_folder_structure("/path/to/folder", max_depth=3)

# Quick preview for import
preview_import("/path/to/folder", max_clients=20)
```

## 🔧 Configuration

### Customize Paths

Edit `data_scraping/config.py`:

```python
GDRIVE_CONFIG = {
    "base_path": "/your/custom/path/to/google/drive",
    "flex_cases_folder": "38_Flex – Business Dev/01_Flex_Cases",
    "flex_subfolder": "02_Flex Offer Files",
    # ...
}
```

### Environment Variable Override

```bash
export GDRIVE_BASE_PATH="/path/to/your/google/drive"
python -m data_scraping.cli import-all
```

## 📁 Expected Folder Structure

Your Google Drive should be organized as:

```
17_Tech/38_Flex – Business Dev/01_Flex_Cases/
├── Client Name (F)/
│   ├── 00_Archive/
│   ├── 01_Daten vom Kunden/
│   ├── 02_Flex Offer Files/          ← This is where runs are
│   │   ├── Run 1/
│   │   │   ├── Input/
│   │   │   │   ├── load_config_XXX.yml
│   │   │   │   └── parameters.json (optional)
│   │   │   └── Output/
│   │   │       ├── kpi_summary_*.csv
│   │   │       └── flex_timeseries_*.csv
│   │   └── Run 2 - Description/
│   │       └── ...
│   ├── 03_Master Files/
│   └── ...
└── Another Client/
    └── ...
```

## 🎯 Key Features

### Smart Client Name Cleaning
Automatically strips suffixes:
- `"Client (F)"` → `"Client"`
- `"Client (Flex)"` → `"Client"`

### Skip Patterns
Automatically skips utility folders:
- Templates (`01_Template`, `02_Template`)
- Archives (`Archive`, `00_Archive`)
- Utility files (`.py`, `.xlsx`, `.txt`)

### Baseline Detection
Automatically identifies baseline configs:
- `0kWh`, `0_battery`, `no_battery`, `baseline`

### Battery Specs Parsing
Extracts capacity/power from config names:
- `"5000kWh_2500kW"` → 5000 kWh, 2500 kW
- `"3280kWh"` → 3280 kWh

## 📈 Import Statistics

After import, you'll see:

```
IMPORT SUMMARY
======================================================================
Clients found:      150
Clients imported:   142
Runs found:         380
Runs imported:      375
Configs imported:   1250
KPIs imported:      15000
======================================================================
```

## 🔍 Verification

After importing, verify your data:

```bash
# Show database summary
python cli.py summary

# Query the data
python cli.py query "SELECT COUNT(*) FROM battery_configs"
python cli.py query "SELECT * FROM v_full_hierarchy LIMIT 10"

# List clients
python cli.py list clients
```

## 🛠 Troubleshooting

### Issue: Path Not Found

**Solution:** Check that:
1. Google Drive is synced and mounted
2. Path in `config.py` matches your system
3. Run `python -m data_scraping.cli show-path` to verify

### Issue: No Data Imported

**Solution:** Verify:
1. Folders have `02_Flex Offer Files` subfolder
2. Run folders contain `Output/` directory
3. Output files match patterns (`kpi_summary*.csv`, etc.)
4. Check skip patterns aren't excluding your data

### Issue: YAML Import Errors

**Solution:** Install PyYAML:
```bash
pip install pyyaml
```

## 📝 Example Workflow

```bash
# 1. Check configuration
python -m data_scraping.cli show-path

# 2. Preview what will be imported
python -m data_scraping.cli preview --max-clients 10

# 3. Do a dry run
python -m data_scraping.cli import-all --dry-run

# 4. Actually import
python -m data_scraping.cli import-all

# 5. Verify in database
python cli.py summary
python cli.py query "SELECT * FROM clients"
```

## 🔗 Integration with Existing CLI

The data scraping module integrates with your existing `cli.py`:

```bash
# After import, use existing commands
python cli.py list clients
python cli.py list configs
python cli.py compare "Georg Jordan GmbH" "Run 1"
python cli.py extract-features
python cli.py train peak_shaving_benefit
```

## 📚 Next Steps

1. **Import your data:**
   ```bash
   python -m data_scraping.cli import-all
   ```

2. **Extract features:**
   ```bash
   python cli.py extract-features
   ```

3. **Train ML models:**
   ```bash
   python cli.py train peak_shaving_benefit
   python cli.py train trading_revenue
   ```

4. **Analyze results:**
   ```bash
   python cli.py compare-models peak_shaving_benefit
   ```

## 💡 Tips

- Start with `preview` to avoid surprises
- Import incrementally using `import-client` for testing
- Check logs if imports fail (errors are printed to console)
- The importer safely handles duplicates (will skip existing data)
- Use `--dry-run` flag to test without making changes

---

**Created:** 2026-01-26  
**Module Version:** 1.0.0  
**Compatible with:** Battery Database v1.0+

