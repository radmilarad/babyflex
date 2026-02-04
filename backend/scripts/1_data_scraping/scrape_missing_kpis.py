"""
Scrape only missing KPIs from KPI sheets into kpi_summary
==========================================================

The KPI file path for each config is read from the battery_configs table
(column kpi_file_path). For each such path (under data_root), the script
scrapes only these 5 source KPIs – and only if they are still missing for
that config in kpi_summary (no overwriting of existing values).

Quelle (String in KPI-Datei)              → Speicherung in kpi_summary (numerisch)
----------------------------------------------------------------------
static_grid_fees   "[wert1, wert2]"       → static_grid_fees_1, static_grid_fees_2
grid_fee_max_load_peak "[wert1, wert2]"   → grid_fee_max_load_peak_1, grid_fee_max_load_peak_2
list_battery_usable_max_state "[wert]"    → list_battery_usable_max_state (eine Zahl)
list_battery_num_annual_cycles "[wert]"   → list_battery_num_annual_cycles (eine Zahl)
list_battery_proportion_hourly_max_load "[wert]" → list_battery_proportion_hourly_max_load (eine Zahl)

Klammern werden entfernt; alle Werte als DOUBLE in kpi_summary.

Wichtig: Liest aus lokalen KPI-Dateien (battery_configs.kpi_file_path unter data_root).
Nicht aus Google Drive – die Pfade in der DB stammen vom vorherigen Import (z.B. import-all).
Wenn unter data_root keine Dateien gefunden werden, werden 0 KPIs geschrieben.

Aufruf (von DB/ aus):
    # Test: nur erste 5 Configs
    python -m 1_data_scraping.cli scrape-missing-kpis --max-configs 5

    # Alle Configs, Standard-DB und data-root (Flex-Cases-Pfad aus config.py)
    python -m 1_data_scraping.cli scrape-missing-kpis

    # Mit explizitem data-root (z.B. lokaler 0_data-Ordner)
    python -m 1_data_scraping.cli scrape-missing-kpis --data-root /pfad/zu/0_data

Optionen:
    --db PATH         DuckDB-Datei (default: database/battery_simulations.duckdb)
    --data-root PATH  Wurzel für kpi_file_path aus battery_configs (default: Flex-Cases-Pfad)
    --max-configs N   Nur erste N Configs verarbeiten (für Tests)
    -q, --quiet       Weniger Ausgabe
"""

import sys
from pathlib import Path
from typing import Optional, List, Tuple, Set

if __name__ == "__main__":
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import pandas as pd

from core.battery_db import BatteryDatabase
from .config import get_flex_cases_path
from .timeseries_loader import resolve_csv_path


# Only these 5 source KPIs; grid-fee → _1/_2 numeric, list_battery_* → single numeric (brackets stripped)
TARGET_KPI_NAMES = [
    "static_grid_fees",
    "grid_fee_max_load_peak",
    "list_battery_usable_max_state",
    "list_battery_num_annual_cycles",
    "list_battery_proportion_hourly_max_load",
]
GRID_FEE_KPIS = {"static_grid_fees", "grid_fee_max_load_peak"}


def _normalize_kpi_name(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    return "_".join(s.split())


def _read_kpi_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        if str(path).lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(path)
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _detect_columns(df: pd.DataFrame) -> tuple:
    if len(df.columns) < 2:
        return None, None, None
    name_col = df.columns[0]
    value_col = df.columns[1]
    for col in df.columns:
        if "name" in str(col).lower() or "kpi" in str(col).lower():
            name_col = col
        elif "value" in str(col).lower():
            value_col = col
    unit_col = next((c for c in df.columns if "unit" in str(c).lower()), None)
    return name_col, value_col, unit_col


def _parse_value(raw_value) -> Tuple[bool, List[float]]:
    """Parse string '[wert1, wert2]' or '[wert]'; return (is_two_values, list of floats)."""
    if pd.isna(raw_value):
        return False, []
    if isinstance(raw_value, (int, float)):
        return False, [float(raw_value)]
    s = str(raw_value).strip()
    # Remove brackets "[...]"
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) == 0:
        return False, []
    try:
        if len(parts) >= 2:
            return True, [float(parts[0]), float(parts[1])]
        return False, [float(parts[0])]
    except ValueError:
        return False, []


def _extract_kpis(df: pd.DataFrame) -> List[Tuple[str, float, Optional[str]]]:
    """
    Extract only the 5 target KPIs. Values are parsed as strings:
    - static_grid_fees / grid_fee_max_load_peak: '[wert1, wert2]' → _1, _2 (numeric)
    - list_battery_*: '[wert]' → single numeric (same name, brackets removed)
    """
    name_col, value_col, unit_col = _detect_columns(df)
    if name_col is None or value_col is None:
        return []
    target_set = {n.lower() for n in TARGET_KPI_NAMES}
    out = []
    for _, row in df.iterrows():
        raw_name = row.get(name_col)
        kpi_name_norm = _normalize_kpi_name(raw_name)
        if kpi_name_norm not in target_set:
            continue
        raw_value = row.get(value_col)
        is_two, values = _parse_value(raw_value)
        if not values:
            continue
        kpi_unit = None
        if unit_col and unit_col in row.index and pd.notna(row.get(unit_col)):
            kpi_unit = str(row[unit_col]).strip()
        canonical = next((n for n in TARGET_KPI_NAMES if n.lower() == kpi_name_norm), None)
        if not canonical:
            continue
        if canonical in GRID_FEE_KPIS and is_two and len(values) == 2:
            out.append((f"{canonical}_1", values[0], kpi_unit))
            out.append((f"{canonical}_2", values[1], kpi_unit))
        elif canonical in GRID_FEE_KPIS and len(values) == 1:
            out.append((f"{canonical}_1", values[0], kpi_unit))
        else:
            # list_battery_usable_max_state, list_battery_num_annual_cycles, list_battery_proportion_hourly_max_load
            # single numeric (brackets already stripped in _parse_value)
            out.append((canonical, values[0], kpi_unit))
    return out


def _get_existing_kpi_names(conn, config_id: int) -> Set[str]:
    rows = conn.execute(
        "SELECT kpi_name FROM kpi_summary WHERE config_id = ?",
        [config_id],
    ).fetchall()
    return {r[0] for r in rows}


def scrape_missing_kpis(
    db_path: str = "database/battery_simulations.duckdb",
    data_root: Optional[Path] = None,
    max_configs: Optional[int] = None,
    config_id_min: Optional[int] = None,
    config_id_max: Optional[int] = None,
    verbose: bool = True,
) -> dict:
    """
    For each config with kpi_file_path: get existing kpi_name from kpi_summary,
    read KPI file, insert only the 5 target KPIs that are missing.
    static_grid_fees / grid_fee_max_load_peak: [val1, val2] → _1, _2 (numeric).
    list_battery_*: [val] → single numeric (brackets removed).
    """
    data_root = data_root or get_flex_cases_path()
    db = BatteryDatabase(db_path)
    conn = db.conn

    sql = """
        SELECT config_id, kpi_file_path
        FROM battery_configs
        WHERE kpi_file_path IS NOT NULL AND kpi_file_path != ''
    """
    params = []
    if config_id_min is not None:
        sql += " AND config_id >= ?"
        params.append(config_id_min)
    if config_id_max is not None:
        sql += " AND config_id <= ?"
        params.append(config_id_max)
    sql += " ORDER BY config_id"
    rows = conn.execute(sql, params).fetchall() if params else conn.execute(sql).fetchall()

    if max_configs and max_configs > 0:
        rows = rows[:max_configs]
        if verbose:
            print(f"Limiting to first {max_configs} configs (test run).", flush=True)
    if config_id_min is not None or config_id_max is not None:
        if verbose:
            print(f"Filter: config_id {config_id_min or '?'} to {config_id_max or '?'}.", flush=True)

    total = len(rows)
    if total == 0:
        if verbose:
            print("No configs with kpi_file_path found.", flush=True)
        db.close()
        return {"configs_processed": 0, "configs_skipped": 0, "kpis_written": 0, "errors": []}

    if verbose:
        print(f"Scraping missing KPIs from {total} configs (targets: {TARGET_KPI_NAMES})...", flush=True)
        print(f"Data root: {data_root}", flush=True)

    try:
        from tqdm import tqdm
        iterator = tqdm(rows, desc="Missing KPIs", unit="config")
    except ImportError:
        iterator = rows

    stats = {
        "configs_processed": 0,
        "configs_skipped": 0,
        "paths_found": 0,
        "paths_not_found": 0,
        "files_empty": 0,
        "configs_with_inserts": 0,
        "kpis_written": 0,
        "errors": [],
    }

    for config_id, kpi_path in iterator:
        path = resolve_csv_path(kpi_path, data_root, verbose=False)
        if not path:
            stats["paths_not_found"] += 1
            stats["configs_skipped"] += 1
            stats["errors"].append(f"config_id={config_id}: path not found under data_root")
            continue
        stats["paths_found"] += 1

        df = _read_kpi_file(path)
        if df.empty:
            stats["files_empty"] += 1
            stats["configs_skipped"] += 1
            continue

        existing = _get_existing_kpi_names(conn, config_id)
        kpi_rows = _extract_kpis(df)
        inserted = 0
        for kpi_name, kpi_value, kpi_unit in kpi_rows:
            if kpi_name in existing:
                continue
            try:
                conn.execute("""
                    INSERT INTO kpi_summary (config_id, kpi_name, kpi_value, kpi_unit)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (config_id, kpi_name) DO UPDATE SET
                        kpi_value = EXCLUDED.kpi_value,
                        kpi_unit = EXCLUDED.kpi_unit
                """, [config_id, kpi_name, kpi_value, kpi_unit])
                stats["kpis_written"] += 1
                inserted += 1
                existing.add(kpi_name)
            except Exception as e:
                stats["errors"].append(f"config_id={config_id} {kpi_name}: {e}")

        if inserted > 0:
            stats["configs_with_inserts"] += 1
        stats["configs_processed"] += 1

    db.close()
    if verbose:
        _print_scrape_summary(stats)
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Scrape only missing: static_grid_fees_1/2, grid_fee_max_load_peak_1/2, list_battery_* (numeric)"
    )
    parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    parser.add_argument("--data-root", type=Path, default=None, help="Data root (default: flex cases path)")
    parser.add_argument("--max-configs", type=int, default=None, metavar="N", help="Only first N configs (test)")
    parser.add_argument("--config-id-min", type=int, default=None, metavar="ID", help="Only config_id >= this")
    parser.add_argument("--config-id-max", type=int, default=None, metavar="ID", help="Only config_id <= this")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less output")
    args = parser.parse_args()

    scrape_missing_kpis(
        db_path=args.db,
        data_root=args.data_root,
        max_configs=args.max_configs,
        config_id_min=getattr(args, "config_id_min", None),
        config_id_max=getattr(args, "config_id_max", None),
        verbose=not args.quiet,
    )


def _print_scrape_summary(stats: dict) -> None:
    """Print clear summary: paths found, KPIs written to DB, and why nothing was written if so."""
    total_configs = stats["configs_processed"] + stats["configs_skipped"]
    paths_ok = stats.get("paths_found", 0)
    paths_fail = stats.get("paths_not_found", 0)
    empty = stats.get("files_empty", 0)
    written = stats.get("kpis_written", 0)
    configs_with_inserts = stats.get("configs_with_inserts", 0)

    print()
    print("--- scrape-missing-kpis summary ---")
    print(f"  Configs with kpi_file_path: {total_configs}")
    print(f"  Paths found under data_root: {paths_ok}  |  Paths not found: {paths_fail}")
    if empty:
        print(f"  Files empty / unreadable: {empty}")
    print(f"  KPIs written to DB (kpi_summary): {written}")
    print(f"  Configs that got at least one new KPI: {configs_with_inserts}")
    if written == 0:
        print()
        print("  No KPIs were written. Possible reasons:")
        if paths_fail > 0:
            print("    - kpi_file_path in battery_configs not found under data_root (wrong --data-root or GDrive not mounted?)")
        if empty > 0:
            print("    - KPI file could not be read or is empty")
        if paths_ok > 0 and empty == 0 and written == 0:
            print("    - No matching rows in file (names: static_grid_fees, grid_fee_max_load_peak, list_battery_usable_max_state, list_battery_num_annual_cycles, list_battery_proportion_hourly_max_load)")
            print("    - Or all those KPIs were already present in kpi_summary for each config")
    print("-----------------------------------")
    if stats.get("errors"):
        for e in stats["errors"][:10]:
            print(f"  ⚠ {e}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")


if __name__ == "__main__":
    main()
