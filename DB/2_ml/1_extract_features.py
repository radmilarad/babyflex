#!/usr/bin/env python3
"""
Step 1: Extraction – Features aus DB erzeugen
=============================================

Lädt Timeseries + KPIs, baut Features, speichert unter 2_ml/artifacts/features/.

Aus Projektroot:  python 2_ml/1_extract_features.py
"""
import sys
import argparse
from pathlib import Path
from importlib import import_module

# Projektroot (übergeordnet von 2_ml/) für Import des Pakets 2_ml
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Paket 2_ml (Modulname mit Ziffer nur per import_module möglich)
try:
    _pipeline = import_module("2_ml.extraction.pipeline")
    FeatureExtractionPipeline = _pipeline.FeatureExtractionPipeline
except ModuleNotFoundError as e:
    if e.name == "duckdb":
        print("Fehler: Modul 'duckdb' fehlt.")
        print("  Lösung: pip install duckdb  oder  pip install -r requirements.txt")
    else:
        print(f"Import-Fehler: {e}")
        print("  Starte vom Projektroot, z.B.: python 2_ml/1_extract_features.py")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Step 1: Extract ML features from battery DB")
    parser.add_argument(
        "--target-kpi",
        default="peak_shaving_benefit",
        help="Target KPI (default: peak_shaving_benefit)",
    )
    parser.add_argument("--no-incremental", action="store_true", help="Re-run all configs")
    parser.add_argument("--reset", action="store_true", 
                        help="Feature-Store leeren und neu bauen. Nötig wenn im Parquet noch alte kpi_*/delta_*-Spalten stehen; danach nur noch Features aus config.py.")
    parser.add_argument("-c", "--client", help="Filter by client name")
    parser.add_argument("--quiet", action="store_true", help="Less output")
    args = parser.parse_args()

    # Pfade immer relativ zur Projektroot (funktioniert egal von wo du startest)
    db_path = str(_root / "database" / "battery_simulations.duckdb")
    store_dir = str(_root / "2_ml" / "artifacts" / "features")
    # Zeitenreihen: timeseries_file_path in DB relativ zu data_root (0_data oder data je nach Import)
    data_root = str(_root / "0_data")

    pipeline = FeatureExtractionPipeline(
        db_path=db_path,
        store_dir=store_dir,
        data_root=data_root,
    )
    if args.reset:
        pipeline.reset()
    df = pipeline.run(
        target_kpi=args.target_kpi,
        incremental=not args.no_incremental,
        client_filter=args.client or None,
        verbose=not args.quiet,
    )
    print(f"\n✅ Step 1 done. Features: {len(df)} Zeilen, {len(df.columns)} Spalten → 2_ml/artifacts/features/")
    print("   Alle Input-Features (ohne IDs/Targets): 2_ml/artifacts/features/feature_list.txt")
    print("   + metadata.json → \"feature_columns\"")

    if len(df) == 0 or len(df.columns) == 0:
        print("\n⚠️  feature_list.txt ist leer, weil der Store leer ist (keine Configs verarbeitet).")
        print("   Neu bauen mit:  python 2_ml/1_extract_features.py --reset --no-incremental")


if __name__ == "__main__":
    main()
