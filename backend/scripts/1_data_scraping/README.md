# Data Scraping

Import von Battery-Simulationen in die DuckDB: Metadaten, KPIs, Pfade zu Zeitreihen-CSVs und (optional) die 4 Zeitreihen-Spalten in `timeseries_ml`.

## Welches Skript ausführen?

**Reihenfolge:**

1. **Scraping** (Metadaten + Pfade in `battery_configs`, KPIs in `kpi_summary`):
   ```bash
   cd DB
   python -m 1_data_scraping.cli import-all
   ```

2. **Zeitreihen in DuckDB laden** (4 Spalten → Tabelle `timeseries_ml`):
   ```bash
   python -m 1_data_scraping.cli load-timeseries
   ```
   Wenn die CSVs unter `0_data` liegen:
   ```bash
   python -m 1_data_scraping.cli load-timeseries --data-root 0_data
   ```

## Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `import-all` | Alle Clients/Runs aus dem konfigurierten Pfad (Google Drive / Flex Cases) importieren |
| `import-client <name>` | Nur einen Client importieren |
| `load-timeseries` | Aus den in `battery_configs.timeseries_file_path` referenzierten CSVs die 4 Spalten (`timestamp_utc`, `grid_load_kwh`, `consumption_load_kwh`, `pv_load_kwh`) in `timeseries_ml` laden |
| `rewrite-paths` | Pfade in der DB umschreiben (z.B. von Emma auf Lucia): Teil vor `/17_Tech` durch `--base` ersetzen; danach funktionieren load-timeseries/Import auf deinem Rechner |
| `preview` | Vorschau, was import-all tun würde |
| `show-path` | Konfigurierten Daten-Pfad anzeigen |

## Konfiguration

Pfad und Muster in `1_data_scraping/config.py` (z. B. `GDRIVE_CONFIG`, `IMPORT_SETTINGS`). Über Umgebungsvariable: `GDRIVE_BASE_PATH`.
