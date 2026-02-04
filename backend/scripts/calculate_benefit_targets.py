#!/usr/bin/env python3
"""
Targets für alle Runs berechnen (ML-Zielvariablen)
==================================================

Berechnet die drei Benefit-Zielvariablen für alle Battery-Configs (pro Run
gegen den 0-Battery-Baseline) und schreibt sie in kpi_summary. Danach liefert
die Feature-Extraktion (1_extract_features.py) target_peak_shaving_benefit,
target_energy_procurement_optimization, target_trading_revenue für das Training.

Formeln (aus core/benefit_calculator.py, BENEFIT_DEFINITIONS):

  1. peak_shaving_benefit [EUR/year]
     = baseline(annual_total_grid_fee_cost_ic) - battery(annual_total_grid_fee_cost_ic)
     → Reduktion der Netzgebühren durch Peak-Shaving (IC-Optimierung).

  2. energy_procurement_optimization [EUR/year]
     = baseline(annual_total_energy_trade_cost_da) - battery(annual_total_energy_trade_cost_da)
     → Einsparung durch optimierte Day-Ahead-Beschaffung.

  3. trading_revenue [EUR/year]
     = (baseline(annual_total_energy_trade_cost_ia) - battery(...)) 
       + (baseline(annual_total_energy_trade_cost_ic) - battery(...))
     → Ertrag aus Intraday- und Regelenergie-/Kontinuierlichem Handel.

Alle Benefits: baseline_value - battery_value (positiv = Einsparung/Ertrag).
Pro Run wird der Baseline (is_baseline = TRUE oder 0-kWh-Config) ermittelt;
alle anderen Configs des Runs werden dagegen berechnet.

Voraussetzungen:
  - kpi_summary enthält die Quell-KPIs pro config_id:
      annual_total_grid_fee_cost_ic
      annual_total_energy_trade_cost_da
      annual_total_energy_trade_cost_ia
      annual_total_energy_trade_cost_ic
  - Pro Run existiert ein Baseline-Config (0 Battery).

Aufruf (von Projektroot DB/):
  python calculate_benefit_targets.py              # Alle Runs, speichern in DB
  python calculate_benefit_targets.py --dry-run    # Nur berechnen, nicht speichern
  python calculate_benefit_targets.py -c "Client"  # Nur einen Client
"""
import sys
from pathlib import Path

# Projektroot = Verzeichnis dieses Skripts (DB/)
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from core import BatteryDatabase, BenefitCalculator


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Calculate benefit targets (peak_shaving, energy_procurement, trading_revenue) for all runs and save to kpi_summary."
    )
    parser.add_argument(
        "-c", "--client",
        help="Only process runs for this client name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate benefits but do not write to database",
    )
    parser.add_argument(
        "--include-baseline",
        action="store_true",
        help="Include baseline configs in output (normally excluded)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Export calculated benefits to CSV (in addition to DB if --save)",
    )
    args = parser.parse_args()

    db_path = str(_root / "database" / "battery_simulations.duckdb")
    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    print("Calculating benefit targets for all runs...")
    print(f"  DB: {db_path}")
    if args.client:
        print(f"  Client filter: {args.client}")
    if args.dry_run:
        print("  Mode: dry-run (no DB write)")

    with BatteryDatabase(db_path) as db:
        calc = BenefitCalculator(db)
        benefits_df = calc.calculate_all_benefits(
            client_name=args.client,
            include_baseline=args.include_baseline,
        )

    if len(benefits_df) == 0:
        print("No benefits calculated. Check that baseline configs exist and kpi_summary has the required KPIs.")
        sys.exit(1)

    print(f"Calculated benefits for {len(benefits_df)} configurations.")

    summary = calc.get_benefit_summary(benefits_df)
    print("\n=== Benefit Summary ===")
    try:
        from tabulate import tabulate
        print(tabulate(summary, headers="keys", tablefmt="psql", showindex=False))
    except ImportError:
        print(summary.to_string(index=False))

    if not args.dry_run:
        with BatteryDatabase(db_path) as db:
            calc = BenefitCalculator(db)
            calc.save_benefits_as_kpis(benefits_df)
        print("\nTargets written to kpi_summary. Re-run 2_ml/1_extract_features.py to refresh feature matrix with target_* columns.")
    else:
        print("\nDry-run: not writing to database. Run without --dry-run to save.")

    if args.output:
        benefits_df.to_csv(args.output, index=False)
        print(f"Exported to: {args.output}")

    print("Done.")


if __name__ == "__main__":
    main()
