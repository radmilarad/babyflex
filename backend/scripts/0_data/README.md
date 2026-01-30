# Data Folder

Drop your simulation data here following this structure:

```
data/
├── ClientA/
│   ├── Run1/
│   │   ├── Input/
│   │   │   └── (input files: .csv, .json, etc.)
│   │   └── Output/
│   │       ├── kpi_summary_no_battery.csv
│   │       ├── kpi_summary_battery_1.csv
│   │       ├── kpi_summary_battery_2.csv
│   │       ├── flex_timeseries_outputs_no_battery.csv
│   │       ├── flex_timeseries_outputs_battery_1.csv
│   │       └── flex_timeseries_outputs_battery_2.csv
│   │
│   └── Run2/
│       ├── Input/...
│       └── Output/...
│
├── ClientB/
│   └── Run1/
│       ├── Input/...
│       └── Output/...
│
└── ...
```

## Naming Conventions

### Folders
- **Client folders**: Any name (e.g., `Acme_Corp`, `Client_A`, `ProjectX`)
- **Run folders**: Any name (e.g., `Run1`, `2024_Q1_Analysis`, `Sizing_Study`)

### Output Files
The importer looks for these patterns in the `Output/` folder:

| File Type | Pattern | Examples |
|-----------|---------|----------|
| KPI Summary | `kpi_summary*.csv` | `kpi_summary_no_battery.csv`, `kpi_summary_battery_1.csv` |
| Timeseries | `flex_timeseries*.csv` | `flex_timeseries_outputs_no_battery.csv`, `flex_timeseries_outputs_battery_1.csv` |

The part after `kpi_summary_` or `flex_timeseries_outputs_` becomes the **config name**.

### Examples
| Filename | Extracted Config Name |
|----------|----------------------|
| `kpi_summary_no_battery.csv` | `no_battery` |
| `kpi_summary_battery_1.csv` | `battery_1` |
| `flex_timeseries_outputs_100kWh_50kW.csv` | `100kWh_50kW` |

## Expected CSV Formats

### KPI Summary CSV
Should have columns for KPI name, value, and optionally unit:

```csv
kpi_name,kpi_value,kpi_unit
annual_energy_cost,15234.50,$
self_consumption_percent,78.5,%
peak_demand_kw,125.3,kW
total_grid_import_kwh,450000,kWh
```

Or any similar format - the importer auto-detects columns containing "name", "value", "unit".

### Timeseries CSV
Any columns are supported. Common examples:

```csv
timestamp,load_kwh,solar_generation_kwh,battery_power_kw,soc_percent,grid_import_kwh
2024-01-01 00:00:00,45.2,0.0,0.0,50.0,45.2
2024-01-01 01:00:00,42.1,0.0,0.0,50.0,42.1
...
```

## Import Command

Once you've added your data, run:

```bash
python3 cli.py import
```

Or from Python:

```python
from battery_db import BatteryDatabase
db = BatteryDatabase()
db.scan_and_import_folder()
db.summary()
```

