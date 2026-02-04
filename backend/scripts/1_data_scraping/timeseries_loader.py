"""
Timeseries Loader – 4 Spalten in DuckDB
======================================

Lädt aus den flex_timeseries-CSVs nur 4 Variablen (umbenannt) in die Tabelle
timeseries_ml. Nach Vorlage des Data-Scraping (gdrive_importer); nutzt
battery_configs.timeseries_file_path.

Spalten-Mapping:
  - ic_grid_load       → grid_load_kwh
  - timestamp_utc       → timestamp_utc
  - consumption_load_0  → consumption_load_kwh
  - pv_load_0           → pv_load_kwh

Usage:
    python -m 1_data_scraping.timeseries_loader [--db PATH] [--data-root PATH] [--truncate]
"""

import sys
from pathlib import Path

# Projektroot (DB/) für battery_db und config
if __name__ == "__main__":
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import duckdb
from typing import Optional

from core.battery_db import BatteryDatabase
from .config import get_flex_cases_path


# Spalten in CSV → Spalten in timeseries_ml
CSV_TO_ML_COLUMNS = {
    "timestamp_utc": "timestamp_utc",
    "ic_grid_load": "grid_load_kwh",
    "consumption_load_0": "consumption_load_kwh",
    "pv_load_0": "pv_load_kwh",
}


def ensure_timeseries_ml_table(conn: duckdb.DuckDBPyConnection):
    """Erstellt timeseries_ml, falls nicht vorhanden."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS timeseries_ml (
            config_id INTEGER NOT NULL REFERENCES battery_configs(config_id),
            timestamp_utc TIMESTAMP NOT NULL,
            grid_load_kwh DOUBLE,
            consumption_load_kwh DOUBLE,
            pv_load_kwh DOUBLE,
            PRIMARY KEY (config_id, timestamp_utc)
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timeseries_ml_config ON timeseries_ml(config_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timeseries_ml_timestamp ON timeseries_ml(timestamp_utc)")
    except Exception:
        pass


# Suffixen wie beim Importer – für Client-Ordner-Mapping
_CLIENT_SUFFIXES = (" (F)", " (Flex)", " - Batterie")


def _clean_client_name(name: str) -> str:
    """Wie Importer: Suffixe vom Client-Namen abziehen."""
    s = name.strip()
    for suffix in _CLIENT_SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _client_folder_map(data_root: Path) -> dict[str, str]:
    """Map: Client-Name (aus DB) -> echter Ordnername unter data_root (z.B. Weihele -> Weihele - Battr #5 (F))."""
    if not data_root.exists() or not data_root.is_dir():
        return {}
    out = {}
    for d in data_root.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            cleaned = _clean_client_name(d.name)
            out[d.name] = d.name
            if cleaned:
                out[cleaned] = d.name
                # DB hat oft nur den ersten Teil (z.B. "Weihele"); Ordner heißt "Weihele - Battr #5 (F)"
                first_word = cleaned.split()[0] if cleaned else ""
                if first_word and first_word not in out:
                    out[first_word] = d.name
    return out


def resolve_csv_path(timeseries_file_path: str, data_root: Optional[Path], verbose: bool = False) -> Optional[Path]:
    """Ergibt absoluten Pfad zur CSV (absolut oder data_root + relativ). Versucht Client-Ordner-Mapping (Weihele -> Weihele - Battr #5 (F))."""
    p = Path(timeseries_file_path)
    if p.exists():
        return p
    if not data_root:
        return None
    if not p.is_absolute():
        candidate = data_root / p
        if candidate.exists():
            return candidate
        # Erster Pfadteil = Client-Name; auf echten Ordner mappen (z.B. Weihele -> Weihele - Battr #5 (F))
        parts = p.parts
        if len(parts) >= 2:
            client_in_path = parts[0]
            rest = Path(*parts[1:])
            try:
                client_map = _client_folder_map(data_root)
                actual_folder = client_map.get(client_in_path) or client_map.get(_clean_client_name(client_in_path))
                if actual_folder:
                    candidate = data_root / actual_folder / rest
                    if candidate.exists():
                        return candidate
                    # DB-Pfad hat evtl. kein "02_Flex Offer Files" – dann dazwischen versuchen
                    if "02_Flex Offer Files" not in parts:
                        candidate = data_root / actual_folder / "02_Flex Offer Files" / rest
                        if candidate.exists():
                            return candidate
            except OSError:
                pass
    return None


def load_timeseries_into_db(
    db_path: str = "database/battery_simulations.duckdb",
    data_root: Optional[Path] = None,
    truncate_first: bool = False,
    verbose: bool = True,
    max_configs: Optional[int] = None,
    skip: Optional[int] = None,
) -> dict:
    """
    Lädt für alle battery_configs mit timeseries_file_path die CSV,
    behält nur die 4 Spalten (umbenannt), und schreibt in timeseries_ml.

    data_root: Basis für relative Pfade (z.B. 0_data); bei None wird
               get_flex_cases_path() genutzt (Google Drive).
    truncate_first: Wenn True, vor dem Laden timeseries_ml leeren.
    max_configs: Wenn gesetzt, nur die ersten N Configs laden (zum Testen).
    skip: Erste N Configs überspringen (z.B. nach Timeout weitermachen ab N+1).
    """
    if verbose:
        print("Opening DB...", flush=True)
    data_root = data_root or get_flex_cases_path()
    db = BatteryDatabase(db_path)
    conn = db.conn

    ensure_timeseries_ml_table(conn)

    if truncate_first:
        conn.execute("DELETE FROM timeseries_ml")
        if verbose:
            print("Cleared timeseries_ml.", flush=True)

    rows = conn.execute("""
        SELECT config_id, timeseries_file_path
        FROM battery_configs
        WHERE timeseries_file_path IS NOT NULL AND timeseries_file_path != ''
    """).fetchall()

    if skip and skip > 0:
        rows = rows[skip:]
        if verbose:
            print(f"Skipping first {skip} configs, {len(rows)} remaining.", flush=True)
    if max_configs is not None and max_configs > 0:
        rows = rows[:max_configs]
        if verbose:
            print(f"Limiting to first {max_configs} configs (test run).", flush=True)

    total = len(rows)
    if total == 0:
        if verbose:
            print("No configs with timeseries_file_path found.", flush=True)
        return {"configs_processed": 0, "configs_skipped": 0, "rows_inserted": 0, "errors": []}

    if verbose:
        print(f"Found {total} configs. Starting...", flush=True)
        print(f"Data root: {data_root}", flush=True)
        # Prüfung mit derselben 1:1-Logik wie beim Laden (erste 5 der zu ladenden Liste)
        print("Path check (first 5 of list to load):", flush=True)
        for cid, tp in rows[:5]:
            resolved = resolve_csv_path(tp, data_root, verbose=False)
            status = "FOUND" if resolved else "NOT FOUND"
            short = (tp[:70] + "…") if len(tp) > 70 else tp
            print(f"  config_id={cid}: {status}  -> {short}", flush=True)
        print("", flush=True)

    try:
        from tqdm import tqdm
        use_tqdm = verbose
    except ImportError:
        use_tqdm = False

    progress = tqdm(enumerate(rows), total=total, desc="Timeseries", unit="config") if use_tqdm else enumerate(rows)
    stats = {"configs_processed": 0, "configs_skipped": 0, "rows_inserted": 0, "errors": []}

    for idx, (config_id, ts_path) in progress:
        path = resolve_csv_path(ts_path, data_root, verbose=False)
        if not path:
            stats["configs_skipped"] += 1
            stats["errors"].append(f"config_id={config_id}: path not found")
            if verbose and not use_tqdm:
                print(f"  [{idx + 1}/{total}] config_id={config_id}: path NOT FOUND, skip", flush=True)
            elif use_tqdm and hasattr(progress, "set_postfix"):
                progress.set_postfix(ok=stats["configs_processed"], skip=stats["configs_skipped"], rows=stats["rows_inserted"])
            continue

        if verbose and not use_tqdm:
            print(f"  [{idx + 1}/{total}] config_id={config_id}: path OK, loading...", flush=True)

        path_str = str(path.resolve())
        path_escaped = path_str.replace("\\", "\\\\").replace("'", "''")
        try:
            conn.execute("DELETE FROM timeseries_ml WHERE config_id = ?", [config_id])
            # Deduplicate by timestamp (DST or string precision can create duplicate keys); normalize to one row per time
            conn.execute(f"""
                INSERT INTO timeseries_ml (config_id, timestamp_utc, grid_load_kwh, consumption_load_kwh, pv_load_kwh)
                SELECT
                    {config_id},
                    ts,
                    MAX(grid_load_kwh),
                    MAX(consumption_load_kwh),
                    MAX(pv_load_kwh)
                FROM (
                    SELECT
                        CAST("timestamp_utc" AS TIMESTAMP) AS ts,
                        "ic_grid_load" AS grid_load_kwh,
                        "consumption_load_0" AS consumption_load_kwh,
                        "pv_load_0" AS pv_load_kwh
                    FROM read_csv_auto('{path_escaped}')
                ) sub
                GROUP BY ts
            """)
            n = conn.execute("SELECT COUNT(*) FROM timeseries_ml WHERE config_id = ?", [config_id]).fetchone()[0]
            stats["rows_inserted"] += n
            stats["configs_processed"] += 1
            if use_tqdm and hasattr(progress, "set_postfix"):
                progress.set_postfix(ok=stats["configs_processed"], skip=stats["configs_skipped"], rows=stats["rows_inserted"])
            elif verbose and not use_tqdm:
                print(f"    -> loaded {n} rows (total: {stats['rows_inserted']} rows, {stats['configs_processed']} ok, {stats['configs_skipped']} skip)", flush=True)
        except Exception as e:
            stats["configs_skipped"] += 1
            msg = f"config_id={config_id}: {e}"
            stats["errors"].append(msg)
            if use_tqdm and hasattr(progress, "set_postfix"):
                progress.set_postfix(ok=stats["configs_processed"], skip=stats["configs_skipped"], rows=stats["rows_inserted"])
            if hasattr(progress, "write"):
                progress.write(f"⚠ {msg}")
            elif verbose and not use_tqdm:
                print(f"    -> ⚠ {e} (skip)", flush=True)

    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Load 4 timeseries columns into timeseries_ml")
    parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    parser.add_argument("--data-root", type=Path, default=None, help="Data root (default: flex cases path)")
    parser.add_argument("--truncate", action="store_true", help="Clear timeseries_ml before loading")
    parser.add_argument("--max-configs", type=int, default=None, metavar="N", help="Only load first N configs (test run)")
    parser.add_argument("--skip", type=int, default=0, metavar="N", help="Skip first N configs (continue after timeout)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less output")
    args = parser.parse_args()

    print("Timeseries loader: 4 columns → timeseries_ml")
    print(f"  DB: {args.db}")
    print(f"  Data root: {args.data_root or get_flex_cases_path()}")
    if args.truncate:
        print("  Truncate: yes")
    if args.max_configs:
        print(f"  Max configs: {args.max_configs} (test run)")
    if args.skip:
        print(f"  Skip first: {args.skip}")
    print()

    stats = load_timeseries_into_db(
        db_path=args.db,
        data_root=args.data_root,
        truncate_first=args.truncate,
        verbose=not args.quiet,
        max_configs=args.max_configs,
        skip=args.skip if args.skip else None,
    )

    print()
    print(f"Processed: {stats['configs_processed']} configs")
    print(f"Skipped:   {stats['configs_skipped']}")
    print(f"Rows:     {stats['rows_inserted']}")
    if stats["errors"]:
        for e in stats["errors"][:10]:
            print(f"  ⚠ {e}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")


if __name__ == "__main__":
    main()
