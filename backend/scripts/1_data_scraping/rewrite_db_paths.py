"""
Pfade in der DB umschreiben (z.B. von Emma auf Lucia)
=====================================================

Ersetzt in runs.folder_path, battery_configs.kpi_file_path und
battery_configs.timeseries_file_path den Teil VOR "/17_Tech" durch
den angegebenen Base-Pfad (damit die DB auf deinem Rechner funktioniert).

Usage:
    python -m 1_data_scraping.rewrite_db_paths
    python -m 1_data_scraping.rewrite_db_paths --base "/Users/lucia/..."
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Projektroot für Imports
if __name__ == "__main__" and __package__ is None:
    _root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(_root))

# Marker im Pfad: ab hier bleibt der Pfad gleich, davor wird ersetzt
PATH_ANCHOR = "17_Tech"

# Dein Base-Pfad (alles VOR /17_Tech)
DEFAULT_NEW_BASE = (
    "/Users/luciacervino/Library/CloudStorage/"
    "GoogleDrive-lucia.cervino@trawa.de/"
    ".shortcut-targets-by-id/1EYADLyWM0Pn5DptM4a9n5frnyGoAnzdp"
)


def rewrite_path(old: str | None, new_base: str) -> str | None:
    """Ersetzt den Teil vor PATH_ANCHOR durch new_base. Bei None oder ohne 17_Tech: unverändert."""
    if not old or not old.strip():
        return old
    if PATH_ANCHOR not in old:
        return old
    idx = old.find(PATH_ANCHOR)
    rest = old[idx:]  # "17_Tech/38_Flex..."
    return new_base.rstrip("/") + "/" + rest


def run(db_path: str, new_base: str, dry_run: bool) -> None:
    import duckdb

    conn = duckdb.connect(db_path)
    updated = {"runs": 0, "kpi_file_path": 0, "timeseries_file_path": 0}

    # runs.folder_path
    rows = conn.execute("SELECT run_id, folder_path FROM runs WHERE folder_path IS NOT NULL").fetchall()
    for run_id, folder_path in rows:
        new_path = rewrite_path(folder_path, new_base)
        if new_path != folder_path:
            if not dry_run:
                conn.execute("UPDATE runs SET folder_path = ? WHERE run_id = ?", [new_path, run_id])
            updated["runs"] += 1
            if dry_run:
                print(f"  run_id={run_id}: .../{new_path[-60:] if len(new_path) > 60 else new_path}")

    # battery_configs.kpi_file_path
    rows = conn.execute(
        "SELECT config_id, kpi_file_path FROM battery_configs WHERE kpi_file_path IS NOT NULL"
    ).fetchall()
    for config_id, kpi_file_path in rows:
        new_path = rewrite_path(kpi_file_path, new_base)
        if new_path != kpi_file_path:
            if not dry_run:
                conn.execute(
                    "UPDATE battery_configs SET kpi_file_path = ? WHERE config_id = ?",
                    [new_path, config_id],
                )
            updated["kpi_file_path"] += 1

    # battery_configs.timeseries_file_path
    rows = conn.execute(
        "SELECT config_id, timeseries_file_path FROM battery_configs WHERE timeseries_file_path IS NOT NULL"
    ).fetchall()
    for config_id, timeseries_file_path in rows:
        new_path = rewrite_path(timeseries_file_path, new_base)
        if new_path != timeseries_file_path:
            if not dry_run:
                conn.execute(
                    "UPDATE battery_configs SET timeseries_file_path = ? WHERE config_id = ?",
                    [new_path, config_id],
                )
            updated["timeseries_file_path"] += 1

    if not dry_run:
        conn.close()

    print(f"Pfade angepasst (new_base = …/{new_base[-50:] if len(new_base) > 50 else new_base})")
    print(f"  runs.folder_path:           {updated['runs']}")
    print(f"  battery_configs.kpi_file_path:      {updated['kpi_file_path']}")
    print(f"  battery_configs.timeseries_file_path: {updated['timeseries_file_path']}")
    if dry_run:
        print("  (Dry-run – keine Änderungen geschrieben)")


# Ersetze "01_Flex_Cases (2)" durch "01_Flex_Cases" in allen Pfad-Spalten
FLEX_CASES_OLD = "01_Flex_Cases (2)"
FLEX_CASES_NEW = "01_Flex_Cases"


def run_fix_flex_cases(db_path: str, dry_run: bool) -> None:
    """Ersetzt in runs und battery_configs '01_Flex_Cases (2)' durch '01_Flex_Cases'."""
    import duckdb

    conn = duckdb.connect(db_path)
    like_arg = f"%{FLEX_CASES_OLD}%"
    counts = {
        "runs": conn.execute("SELECT COUNT(*) FROM runs WHERE folder_path LIKE ?", [like_arg]).fetchone()[0],
        "kpi_file_path": conn.execute("SELECT COUNT(*) FROM battery_configs WHERE kpi_file_path LIKE ?", [like_arg]).fetchone()[0],
        "timeseries_file_path": conn.execute("SELECT COUNT(*) FROM battery_configs WHERE timeseries_file_path LIKE ?", [like_arg]).fetchone()[0],
    }

    if not dry_run and (counts["runs"] or counts["kpi_file_path"] or counts["timeseries_file_path"]):
        conn.execute(
            "UPDATE runs SET folder_path = REPLACE(folder_path, ?, ?) WHERE folder_path LIKE ?",
            [FLEX_CASES_OLD, FLEX_CASES_NEW, like_arg],
        )
        conn.execute(
            "UPDATE battery_configs SET kpi_file_path = REPLACE(kpi_file_path, ?, ?) WHERE kpi_file_path LIKE ?",
            [FLEX_CASES_OLD, FLEX_CASES_NEW, like_arg],
        )
        conn.execute(
            "UPDATE battery_configs SET timeseries_file_path = REPLACE(timeseries_file_path, ?, ?) WHERE timeseries_file_path LIKE ?",
            [FLEX_CASES_OLD, FLEX_CASES_NEW, like_arg],
        )
    conn.close()

    print(f"Replace '{FLEX_CASES_OLD}' → '{FLEX_CASES_NEW}'")
    print(f"  runs.folder_path:             {counts['runs']}")
    print(f"  battery_configs.kpi_file_path:        {counts['kpi_file_path']}")
    print(f"  battery_configs.timeseries_file_path: {counts['timeseries_file_path']}")
    if dry_run:
        print("  (Dry-run – keine Änderungen geschrieben)")


def main():
    parser = argparse.ArgumentParser(description="Pfade in der DB anpassen")
    parser.add_argument("--db", default="database/battery_simulations.duckdb", help="Pfad zur DuckDB-Datei")
    parser.add_argument("--base", default=DEFAULT_NEW_BASE, help="Neuer Base-Pfad (alles vor /17_Tech)")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts schreiben")
    parser.add_argument("--fix-flex-cases", action="store_true", help="01_Flex_Cases (2) → 01_Flex_Cases ersetzen")
    args = parser.parse_args()

    if args.fix_flex_cases:
        run_fix_flex_cases(args.db, args.dry_run)
    else:
        run(args.db, args.base.strip(), args.dry_run)


if __name__ == "__main__":
    main()
