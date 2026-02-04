#!/usr/bin/env python3
"""
Step 1: Extraction – Features aus battery_simulations extrahieren
=================================================================

Nutzt 2_ml/config_feature_extraction.py als Quelle für die Feature-Definition.
Das feature_set in der DB wird daraus abgeleitet und in feature_sets gespeichert.

Ablauf (pro battery_config):
  1. Configs laden: get_all_configs(target_kpi) → battery_configs + target aus kpi_summary.
  2. Direct inputs: Namen aus config.DIRECT_INPUT_NAMES.
     - Zuerst aus Metadata (battery_configs: battery_capacity_kwh, battery_power_kw, …).
     - Fehlende aus kpi_summary (z.B. list_battery_usable_max_state, static_grid_fees,
       grid_fee_max_load_peak, pv_annual_total). Diese KPIs müssen in kpi_summary existieren.
  3. Load-profile-Features: Zeitreihen-CSV unter data_root + timeseries_file_path laden.
     - Pfad = data_root / timeseries_file_path (kein Client-Mapping wie beim KPI-Scraper).
     - Wenn die Datei nicht existiert → ts_df leer → nur direct inputs, keine ts__-Features.
  4. feature_set: Ein Eintrag in feature_sets mit feature_set_name = "default". Enthält
     feature_config (direct_input_names, load_profile_column_specs, …) aus config_feature_extraction.py.
     Pro config_id eine Zeile in ml_features mit features (JSON) und feature_set_id.

Speicherung:
  - 2_ml/artifacts/features/ (Parquet, metadata.json, feature_list.txt, processed_configs.json).
  - DuckDB: feature_sets (ein Eintrag "default") + ml_features (pro config_id + feature_set_id).

Häufige Gründe, warum die Extraktion „nicht richtig“ wirkt:
  - data_root falsch: timeseries_file_path in battery_configs ist relativ zu data_root. Wenn
    die DB-Pfade von GDrive/Flex Cases stammen, muss data_root auf den gleichen Wurzelordner
    zeigen (z.B. Flex-Cases-Pfad), nicht auf 0_data. Sonst werden keine Zeitreihen geladen
    → keine load-profile-Features (ts__*, ratio, etc.), nur direct inputs.
  - Direct-KPIs fehlen: Alle Namen in DIRECT_INPUT_NAMES müssen in kpi_summary vorkommen
    (pro config_id), sonst NaN. Z.B. static_grid_fees/grid_fee_max_load_peak müssen als
    einzelner Wert in kpi_summary stehen (ggf. vorher resolve-grid-fee-kpis ausführen).
  - Keine Configs zu verarbeiten: Bei --no-incremental werden nur Configs verarbeitet, die
    noch nicht in processed_configs stehen. Mit --reset --no-incremental von vorn.
  - target_kpi fehlt: Configs werden trotzdem geladen (LEFT JOIN), target ist dann NaN.

Aufruf (von Projektroot DB/):
  python 2_ml/1_extract_features.py
  python 2_ml/1_extract_features.py --data-root /pfad/zu/flex_cases  # wenn Zeitreihen dort
  python 2_ml/1_extract_features.py --reset --no-incremental        # komplette Neu-Extraktion
  python 2_ml/1_extract_features.py --refresh-targets              # nur target_* aus kpi_summary (nach calculate_benefit_targets.py)
  python 2_ml/1_extract_features.py --only-features ts__usage_hours   # nur dieses Feature nachziehen, Rest der Matrix bleibt
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
    parser = argparse.ArgumentParser(
        description="Step 1: Extract ML features from battery_simulations (config_feature_extraction → DB + artifacts)"
    )
    parser.add_argument(
        "--target-kpi",
        default="peak_shaving_benefit",
        help="Target KPI (default: peak_shaving_benefit)",
    )
    parser.add_argument("--no-incremental", action="store_true", help="Re-run all configs")
    parser.add_argument("--reset", action="store_true", 
                        help="Feature-Store leeren und neu bauen. Nötig wenn im Parquet noch alte kpi_*/delta_*-Spalten stehen; danach nur noch Features aus config_feature_extraction.")
    parser.add_argument("--no-db", action="store_true", 
                        help="Features nur in 2_ml/artifacts/ speichern, nicht in die DB (feature_sets/ml_features) schreiben.")
    parser.add_argument("--refresh-targets", action="store_true",
                        help="Nur Target-Spalten (target_*) aus kpi_summary aktualisieren; keine Neu-Extraktion der Features. Nach calculate_benefit_targets.py.")
    parser.add_argument("--only-features", type=str, nargs="+", metavar="FEATURE",
                        help="Nur diese load-profile-Features nachziehen (z.B. ts__usage_hours oder usage_hours). Ersetzt/ergänzt Spalten in der bestehenden Matrix; keine Voll-Extraktion.")
    parser.add_argument("-c", "--client", help="Filter by client name")
    parser.add_argument("--data-root", default=None, help="Wurzel für timeseries_file_path (default: 0_data). Muss der Ordner sein, unter dem die Pfade aus battery_configs existieren (z.B. Flex-Cases-Pfad).")
    parser.add_argument("--quiet", action="store_true", help="Less output")
    args = parser.parse_args()

    # Pfade immer relativ zur Projektroot (funktioniert egal von wo du startest)
    db_path = str(_root / "database" / "battery_simulations.duckdb")
    store_dir = str(_root / "2_ml" / "artifacts" / "features")
    # Zeitreihen: timeseries_file_path in DB ist relativ zu data_root
    data_root = args.data_root if args.data_root else str(_root / "0_data")

    pipeline = FeatureExtractionPipeline(
        db_path=db_path,
        store_dir=store_dir,
        data_root=data_root,
        save_to_db=not args.no_db,
    )
    if args.refresh_targets:
        if not args.quiet:
            print("Refreshing target columns from kpi_summary only…", flush=True)
            print(f"  DB: {db_path}", flush=True)
        df = pipeline.refresh_targets_only(verbose=not args.quiet)
        print(f"\n✅ Targets refreshed. Features: {len(df)} Zeilen, {len(df.columns)} Spalten → 2_ml/artifacts/features/")
        if len(df) == 0 or len(df.columns) == 0:
            print("\n⚠️  Keine Feature-Matrix vorhanden. Zuerst volle Extraktion: python 2_ml/1_extract_features.py --reset --no-incremental")
        return

    if args.only_features:
        if not args.quiet:
            print("Only-features: nur angegebene Spalten nachziehen…", flush=True)
            print(f"  Features: {args.only_features}", flush=True)
            print(f"  DB: {db_path}", flush=True)
        df = pipeline.run_only_features(
            feature_names=args.only_features,
            target_kpi=args.target_kpi,
            client_filter=args.client or None,
            verbose=not args.quiet,
        )
        print(f"\n✅ Only-features done. Matrix: {len(df)} Zeilen, {len(df.columns)} Spalten → 2_ml/artifacts/features/")
        return

    if args.reset:
        pipeline.reset()
    if not args.quiet:
        print("Running feature extraction (progress below)…", flush=True)
        print(f"  DB: {db_path}", flush=True)
        print(f"  data_root (Zeitreihen): {data_root}", flush=True)
        print("", flush=True)
    df = pipeline.run(
        target_kpi=args.target_kpi,
        incremental=not args.no_incremental,
        client_filter=args.client or None,
        verbose=not args.quiet,
    )
    print(f"\n✅ Step 1 done. Features: {len(df)} Zeilen, {len(df.columns)} Spalten → 2_ml/artifacts/features/")
    if not args.no_db:
        print("   DB: feature_sets (default) + ml_features befüllt.")
    print("   Alle Input-Features (ohne IDs/Targets): 2_ml/artifacts/features/feature_list.txt")
    print("   + metadata.json → \"feature_columns\"")

    if len(df) == 0 or len(df.columns) == 0:
        print("\n⚠️  feature_list.txt ist leer, weil der Store leer ist (keine Configs verarbeitet).")
        print("   Neu bauen mit:  python 2_ml/1_extract_features.py --reset --no-incremental")


if __name__ == "__main__":
    main()
