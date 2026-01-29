# Battery Simulation Database

A DuckDB-based system for storing and querying battery simulation results with a hierarchical structure.

## Structure

```
Battery_Database/
├── database/
│   ├── schema.sql              # Database schema
│   └── battery_simulations.duckdb  # DuckDB database file
├── data/                       # Raw data files
│   ├── Client_A/
│   │   ├── Run_1/
│   │   │   ├── Input/
│   │   │   │   └── parameters.json
│   │   │   └── Output/
│   │   │       ├── kpi_summary_0_battery.csv
│   │   │       ├── kpi_summary_100kWh_50kW.csv
│   │   │       ├── flex_timeseries_0_battery.csv
│   │   │       └── flex_timeseries_100kWh_50kW.csv
│   │   └── Run_2/
│   │       └── ...
│   └── Client_B/
│       └── ...
├── battery_db.py               # Main database interface
├── cli.py                      # Command-line interface
└── examples/
    └── create_sample_data.py   # Generate sample data
```

## Quick Start

### 1. Venv aktivieren & Abhängigkeiten installieren

**Venv aktivieren (macOS/Linux):**
```bash
source .venv/bin/activate
```

Falls nach dem Aktivieren `pip` nicht gefunden wird, Pakete trotzdem mit dem Python der venv installieren (ohne `pip` im PATH):

```bash
# Im Projektroot (Battery_Database):
.venv/bin/python -m pip install -r requirements.txt
```

Ohne venv aktivieren geht auch:
```bash
.venv/bin/python -m pip install -r requirements.txt
```

**macOS: Meldung „nicht öffnen – Apple konnte Integrität nicht prüfen“ (z. B. `lib.cpython-313-darwin.so`):**  
Gatekeeper blockiert Python-Bibliotheken. Auf **„Fertig“** klicken (nicht „In den Papierkorb“). Dann im Projektroot die Quarantäne der venv entfernen:

```bash
xattr -cr .venv
```

Danach Skripte erneut mit `.venv/bin/python …` starten.

### 2. Install Dependencies (falls venv schon aktiv und pip vorhanden)

```bash
pip install -r requirements.txt
# oder: python -m pip install -r requirements.txt
```

### 3. Initialize & Create Sample Data

```bash
# Initialize the database
python cli.py init

# Create sample data to explore
python examples/create_sample_data.py
```

### 4. Explore the Database

```bash
# View summary
python cli.py summary

# List all clients
python cli.py list clients

# List runs for a client
python cli.py list runs -f Acme_Corp

# List battery configurations
python cli.py list configs -f Acme_Corp

# Compare configurations within a run
python cli.py compare Acme_Corp 2024_Sizing_Study

# Compare a specific KPI
python cli.py compare Acme_Corp 2024_Sizing_Study annual_energy_cost
```

## Python API Usage

```python
from battery_db import BatteryDatabase

# Connect to database
db = BatteryDatabase()

# Add a client
db.add_client("NewClient", "Description")

# Add a simulation run
db.add_run(
    client_name="NewClient",
    run_name="2024_Analysis",
    run_description="Annual battery sizing study",
    input_parameters={
        "tariff": "TOU",
        "solar_capacity_kw": 100
    }
)

# Add battery configurations
db.add_battery_config(
    client_name="NewClient",
    run_name="2024_Analysis",
    config_name="0_battery",
    is_baseline=True,
    battery_capacity_kwh=0,
    battery_power_kw=0,
    kpi_file="kpi_summary_0_battery.csv",
    timeseries_file="flex_timeseries_0_battery.csv"
)

db.add_battery_config(
    client_name="NewClient",
    run_name="2024_Analysis",
    config_name="100kWh_50kW",
    is_baseline=False,
    battery_capacity_kwh=100,
    battery_power_kw=50,
    battery_efficiency=0.92,
    kpi_file="kpi_summary_100kWh_50kW.csv",
    timeseries_file="flex_timeseries_100kWh_50kW.csv"
)

# Query data
clients = db.get_clients()
runs = db.get_runs("NewClient")
configs = db.get_battery_configs("NewClient", "2024_Analysis")

# Query timeseries directly from CSV (DuckDB magic!)
ts_data = db.query_timeseries_csv("NewClient", "2024_Analysis", "100kWh_50kW")

# Compare configurations
comparison = db.compare_configs("NewClient", "2024_Analysis", "annual_energy_cost")

# Run custom SQL
result = db.execute("""
    SELECT c.client_name, r.run_name, bc.config_name, kpi.kpi_value
    FROM kpi_summary kpi
    JOIN battery_configs bc ON kpi.config_id = bc.config_id
    JOIN runs r ON bc.run_id = r.run_id
    JOIN clients c ON r.client_id = c.client_id
    WHERE kpi.kpi_name = 'annual_energy_cost'
    ORDER BY kpi.kpi_value
""")

# Show summary
db.summary()

# Clean up
db.close()
```

## Import Existing Data

If you have an existing folder structure with simulation outputs:

```bash
# Import from the default data/ folder
python cli.py import

# Import from a specific path
python cli.py import /path/to/existing/data
```

The importer expects this structure:
```
Client_Name/
├── Run_Name/
│   ├── Input/
│   │   └── parameters.json  (optional)
│   └── Output/
│       ├── kpi_summary_*.csv
│       └── flex_timeseries_*.csv
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `python cli.py init` | Initialize the database |
| `python cli.py add-client <name>` | Add a new client |
| `python cli.py add-run <client> <run>` | Add a new run |
| `python cli.py add-config <client> <run> <config>` | Add a battery config |
| `python cli.py import [path]` | Import from folder structure |
| `python cli.py list clients` | List all clients |
| `python cli.py list runs [-f client]` | List runs |
| `python cli.py list configs [-f client]` | List configurations |
| `python cli.py summary` | Show database summary |
| `python cli.py compare <client> <run> [kpi]` | Compare configs |
| `python cli.py view-ts <client> <run> <config>` | View timeseries |
| `python cli.py query "<sql>"` | Run custom SQL |
| `python cli.py export "<sql>" -o output.csv` | Export to CSV |


## Expected CSV Formats

### KPI Summary CSV
```csv
kpi_name,kpi_value,kpi_unit
annual_energy_cost,15234.50,$
self_consumption_percent,78.5,%
peak_demand_kw,125.3,kW
```

### Timeseries CSV
```csv
timestamp,load_kwh,solar_generation_kwh,battery_power_kw,soc_percent,grid_import_kwh
2024-01-01 00:00:00,45.2,0.0,0.0,50.0,45.2
2024-01-01 01:00:00,42.1,0.0,0.0,50.0,42.1
```

