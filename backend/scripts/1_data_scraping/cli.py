#!/usr/bin/env python3
"""
Data Scraping CLI
=================

Import Metadaten + KPIs + Pfade → battery_configs/kpi_summary.
Laden der 4 Zeitreihen-Spalten → timeseries_ml.

Usage (von DB/ aus):
    python -m 1_data_scraping.cli import-all      # Scraping (Metadaten + Pfade)
    python -m 1_data_scraping.cli load-timeseries # Zeitreihen in DuckDB
    python 1_data_scraping/cli.py import-all      # geht auch (startet als Modul)
"""
# Wenn direkt als Skript gestartet (nicht als Modul): als Modul neu starten
if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))
    import subprocess
    sys.exit(subprocess.run(
        [sys.executable, "-m", "1_data_scraping.cli"] + sys.argv[1:],
        cwd=str(_root),
    ).returncode)

import argparse
import sys
from pathlib import Path

from .gdrive_importer import GDriveImporter
from .config import get_flex_cases_path, get_flex_cases_path_both
from .timeseries_loader import load_timeseries_into_db, resolve_csv_path
from .rewrite_db_paths import run as rewrite_db_paths_run, run_fix_flex_cases
from .scrape_missing_kpis import scrape_missing_kpis


def cmd_preview(args):
    """Preview what will be imported from Google Drive."""
    with GDriveImporter() as importer:
        importer.preview(max_clients=args.max_clients)


def cmd_import_all(args):
    """Import all data from Google Drive."""
    with GDriveImporter() as importer:
        stats = importer.import_all(dry_run=args.dry_run)
        
        if not args.dry_run:
            print(f"\n✅ Successfully imported:")
            print(f"   {stats['clients_imported']} clients")
            print(f"   {stats['runs_imported']} runs")
            print(f"   {stats['configs_imported']} configurations")
            print(f"   {stats['kpis_imported']} KPIs")


def cmd_import_client(args):
    """Import a specific client."""
    with GDriveImporter() as importer:
        success = importer.import_client(args.client_name)
        if success:
            print(f"✅ Successfully imported {args.client_name}")
        else:
            print(f"❌ Failed to import {args.client_name}")
            sys.exit(1)


def cmd_show_path(args):
    """Show the configured Google Drive path."""
    path = get_flex_cases_path()
    print(f"Google Drive Flex Cases Path:")
    print(f"  {path}")
    print(f"\nExists: {'✅ Yes' if path.exists() else '❌ No'}")
    
    if path.exists():
        client_count = sum(1 for f in path.iterdir() if f.is_dir() and not f.name.startswith('.'))
        print(f"Client folders: {client_count}")


def cmd_check_paths(args):
    """Show stored timeseries paths and whether they exist (no loading)."""
    from pathlib import Path
    from core.battery_db import BatteryDatabase
    db = BatteryDatabase(args.db)
    rows = db.conn.execute("""
        SELECT config_id, timeseries_file_path
        FROM battery_configs
        WHERE timeseries_file_path IS NOT NULL AND timeseries_file_path != ''
        LIMIT ?
    """, [args.limit]).fetchall()
    db.close()

    # Dein Pfad: Ordner, der die Client-Ordner (Weihele, …) enthält
    if getattr(args, "my_path", None):
        my_root = Path(args.my_path).expanduser().resolve()
        print("Prüfe mit deinem Pfad:\n")
        print(f"  Dein Pfad: {my_root}")
        print(f"  Existiert Ordner? {my_root.exists()}\n")
        if not my_root.exists():
            print("  → Ordner nicht gefunden. Pfad prüfen (Tippfehler, Leerzeichen, Anführungszeichen).")
            return
        print(f"  Erste {len(rows)} Einträge aus der DB (relative Pfade) – wird darunter gesucht:\n")
        found = 0
        for config_id, tp in rows:
            p = Path(tp)
            if p.is_absolute():
                full = p
                exists = p.exists()
            else:
                full = my_root / tp
                exists = full.exists()
            if exists:
                found += 1
            status = "✓ gefunden" if exists else "✗ nicht gefunden"
            print(f"  config_id={config_id}: {status}")
            print(f"    DB hat: {tp[:75]}{'…' if len(tp) > 75 else ''}")
            if not exists and not p.is_absolute():
                print(f"    Gesucht in: {full}")
            print()
        print(f"  Zusammenfassung: {found}/{len(rows)} Dateien unter deinem Pfad gefunden.")
        if found == 0 and rows:
            print("\n  → Der Ordner muss die Client-Ordner (z.B. Weihele) enthalten,")
            print("     und darin Run-Ordner mit …/Output/flex_timeseries_….csv")
        return

    if args.try_both:
        root_without, root_with_2 = get_flex_cases_path_both()
        print("Prüfe beide Optionen (relative Pfade aus DB):\n")
        print(f"  Option A (01_Flex_Cases):     {root_without}")
        print(f"  Option B (01_Flex_Cases (2)): {root_with_2}\n")
        print(f"  Existieren die Ordner? A={root_without.exists()}, B={root_with_2.exists()}\n")
        print(f"First {len(rows)} configs:\n")
        for config_id, tp in rows:
            p = Path(tp)
            if p.is_absolute():
                found_a = found_b = p.exists()
                print(f"  config_id={config_id}: absoluter Pfad -> exists={found_a}")
            else:
                found_a = (root_without / tp).exists()
                found_b = (root_with_2 / tp).exists()
                print(f"  config_id={config_id}: unter A (01_Flex_Cases): {'✓' if found_a else '✗'}  |  unter B (01_Flex_Cases (2)): {'✓' if found_b else '✗'}")
            print(f"    {tp[:80]}{'…' if len(tp) > 80 else ''}")
        if not rows:
            print("  No configs with timeseries_file_path.")
        return

    data_root = Path(args.data_root) if args.data_root else get_flex_cases_path()
    print(f"Data root: {data_root}\n")
    print(f"First {len(rows)} timeseries_file_path from DB:\n")
    for config_id, tp in rows:
        p = Path(tp)
        direct = p.exists()
        under = (data_root / tp).exists() if tp and not p.is_absolute() else False
        status = "OK (direct)" if direct else ("OK (under data_root)" if under else "NOT FOUND")
        print(f"  config_id={config_id}: {status}")
        print(f"    {tp[:90]}{'…' if len(tp) > 90 else ''}")
    if not rows:
        print("  No configs with timeseries_file_path.")


def cmd_check_kpi_paths(args):
    """Test that kpi_file_path from battery_configs resolve to existing files (same logic as scrape-missing-kpis)."""
    from core.battery_db import BatteryDatabase
    limit = getattr(args, "limit", 20)
    data_root = Path(args.data_root) if args.data_root else get_flex_cases_path()
    db = BatteryDatabase(args.db)
    rows = db.conn.execute("""
        SELECT config_id, kpi_file_path
        FROM battery_configs
        WHERE kpi_file_path IS NOT NULL AND kpi_file_path != ''
        ORDER BY config_id
        LIMIT ?
    """, [limit]).fetchall()
    db.close()

    print(f"Checking KPI file paths (same resolution as scrape-missing-kpis)\n")
    print(f"  Data root: {data_root}")
    print(f"  Limit: first {len(rows)} configs\n")
    if not rows:
        print("  No configs with kpi_file_path in battery_configs.")
        return

    found = 0
    for config_id, kpi_path in rows:
        resolved = resolve_csv_path(kpi_path, data_root, verbose=False)
        exists = resolved is not None and resolved.exists()
        if exists:
            found += 1
        status = "✓ found" if exists else "✗ NOT FOUND"
        print(f"  config_id={config_id}: {status}")
        print(f"    DB path: {kpi_path[:85]}{'…' if len(kpi_path) > 85 else ''}")
        if resolved is not None:
            print(f"    Resolved: {resolved}")
        else:
            print(f"    Resolved: (none – path could not be resolved under data_root)")
        print()
    print(f"  Summary: {found}/{len(rows)} KPI files found.")
    if found == 0 and rows:
        print("\n  → Check --data-root; paths in DB are relative to that (or absolute).")


def cmd_fix_flex_cases(args):
    """Replace '01_Flex_Cases (2)' with '01_Flex_Cases' in all path columns."""
    run_fix_flex_cases(db_path=args.db, dry_run=args.dry_run)


def cmd_rewrite_paths(args):
    """Rewrite DB paths (e.g. from Emma to Lucia): replace prefix before /17_Tech with --base."""
    rewrite_db_paths_run(
        db_path=args.db,
        new_base=args.base.strip(),
        dry_run=args.dry_run,
    )


def cmd_scrape_missing_kpis(args):
    """Scrape only KPIs that are missing in kpi_summary (reads local KPI files under data_root; see summary for paths/DB writes)."""
    data_root = Path(args.data_root) if args.data_root else None
    scrape_missing_kpis(
        db_path=args.db,
        data_root=data_root,
        max_configs=getattr(args, "max_configs", None),
        config_id_min=getattr(args, "config_id_min", None),
        config_id_max=getattr(args, "config_id_max", None),
        verbose=not getattr(args, "quiet", False),
    )
    print("✅ Done.")


def cmd_load_timeseries(args):
    """Load 4 timeseries columns (grid_load_kwh, consumption_load_kwh, pv_load_kwh, timestamp_utc) into timeseries_ml."""
    data_root = Path(args.data_root) if args.data_root else None
    stats = load_timeseries_into_db(
        db_path=args.db,
        data_root=data_root,
        truncate_first=args.truncate,
        verbose=not args.quiet,
        max_configs=getattr(args, "max_configs", None),
        skip=getattr(args, "skip", 0) or None,
    )
    print(f"\n✅ Processed: {stats['configs_processed']} configs, {stats['rows_inserted']} rows")
    if stats["configs_skipped"]:
        print(f"   Skipped: {stats['configs_skipped']}")
    if stats["errors"]:
        for e in stats["errors"][:5]:
            print(f"   ⚠ {e}")
        if len(stats["errors"]) > 5:
            print(f"   ... and {len(stats['errors']) - 5} more")


def main():
    parser = argparse.ArgumentParser(
        description="Data Scraping CLI for Battery Database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Preview command
    preview_parser = subparsers.add_parser("preview", help="Preview import")
    preview_parser.add_argument(
        "--max-clients", 
        type=int, 
        default=10,
        help="Maximum number of clients to preview (default: 10)"
    )
    preview_parser.set_defaults(func=cmd_preview)
    
    # Import all command
    import_parser = subparsers.add_parser("import-all", help="Import all data")
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't actually import"
    )
    import_parser.set_defaults(func=cmd_import_all)
    
    # Import client command
    client_parser = subparsers.add_parser("import-client", help="Import specific client")
    client_parser.add_argument("client_name", help="Name of the client to import")
    client_parser.set_defaults(func=cmd_import_client)
    
    # Show path command
    path_parser = subparsers.add_parser("show-path", help="Show configured Google Drive path")
    path_parser.set_defaults(func=cmd_show_path)

    # 01_Flex_Cases (2) → 01_Flex_Cases in allen Pfad-Spalten
    fix_flex_parser = subparsers.add_parser("fix-flex-cases", help="Replace '01_Flex_Cases (2)' with '01_Flex_Cases' in DB paths")
    fix_flex_parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    fix_flex_parser.add_argument("--dry-run", action="store_true", help="Only show counts, don't update")
    fix_flex_parser.set_defaults(func=cmd_fix_flex_cases)

    # Check stored paths (ohne zu laden)
    check_parser = subparsers.add_parser("check-paths", help="Show stored timeseries paths and whether they exist")
    check_parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    check_parser.add_argument("--data-root", default=None, help="Data root (default: flex cases path)")
    check_parser.add_argument("--my-path", dest="my_path", default=None, metavar="PATH", help="Dein vollständiger Pfad zum Ordner, der die Client-Ordner (z.B. Weihele) enthält – prüft ob die DB-Pfade darunter existieren")
    check_parser.add_argument("--limit", type=int, default=10, help="Number of paths to show (default: 10)")
    check_parser.add_argument("--try-both", action="store_true", help="Check both 01_Flex_Cases and 01_Flex_Cases (2)")
    check_parser.set_defaults(func=cmd_check_paths)

    # Check KPI file paths (battery_configs.kpi_file_path) – same resolution as scrape-missing-kpis
    kpi_paths_parser = subparsers.add_parser("check-kpi-paths", help="Test that kpi_file_path from battery_configs resolve to existing files (first 20 configs)")
    kpi_paths_parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    kpi_paths_parser.add_argument("--data-root", default=None, help="Data root (default: flex cases path)")
    kpi_paths_parser.add_argument("--limit", type=int, default=20, help="Number of configs to check (default: 20)")
    kpi_paths_parser.set_defaults(func=cmd_check_kpi_paths)

    # Rewrite DB paths (z.B. Emma → Lucia: alles vor /17_Tech ersetzen)
    rewrite_parser = subparsers.add_parser("rewrite-paths", help="Rewrite DB paths to your machine (prefix before /17_Tech)")
    rewrite_parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    rewrite_parser.add_argument(
        "--base",
        default="/Users/luciacervino/Library/CloudStorage/GoogleDrive-lucia.cervino@trawa.de/.shortcut-targets-by-id/1EYADLyWM0Pn5DptM4a9n5frnyGoAnzdp",
        help="Your base path (everything before /17_Tech)",
    )
    rewrite_parser.add_argument("--dry-run", action="store_true", help="Show what would be changed, don't write")
    rewrite_parser.set_defaults(func=cmd_rewrite_paths)

    # Load timeseries into DuckDB (4 columns: grid_load_kwh, consumption_load_kwh, pv_load_kwh, timestamp_utc)
    ts_parser = subparsers.add_parser("load-timeseries", help="Load 4 timeseries columns into timeseries_ml")
    ts_parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    ts_parser.add_argument("--data-root", default=None, help="Data root (e.g. 0_data); default: flex cases path")
    ts_parser.add_argument("--truncate", action="store_true", help="Clear timeseries_ml before loading")
    ts_parser.add_argument("--max-configs", type=int, default=None, metavar="N", help="Only load first N configs (test run)")
    ts_parser.add_argument("--skip", type=int, default=0, metavar="N", help="Skip first N configs (continue after timeout)")
    ts_parser.add_argument("-q", "--quiet", action="store_true", help="Less output")
    ts_parser.set_defaults(func=cmd_load_timeseries)

    # Scrape only missing: static_grid_fees_1/2, grid_fee_max_load_peak_1/2, list_battery_* (numeric)
    missing_parser = subparsers.add_parser("scrape-missing-kpis", help="Scrape only missing: grid-fee _1/_2 + list_battery_* (numeric)")
    missing_parser.add_argument("--db", default="database/battery_simulations.duckdb", help="DuckDB path")
    missing_parser.add_argument("--data-root", default=None, help="Data root (default: flex cases path)")
    missing_parser.add_argument("--max-configs", type=int, default=None, metavar="N", help="Only first N configs (test)")
    missing_parser.add_argument("--config-id-min", type=int, default=None, metavar="ID", help="Only config_id >= ID")
    missing_parser.add_argument("--config-id-max", type=int, default=None, metavar="ID", help="Only config_id <= ID")
    missing_parser.add_argument("-q", "--quiet", action="store_true", help="Less output")
    missing_parser.set_defaults(func=cmd_scrape_missing_kpis)

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if "--debug" in sys.argv:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
