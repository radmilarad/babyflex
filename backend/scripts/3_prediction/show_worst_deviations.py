#!/usr/bin/env python3
"""
Zeigt die N Configs mit der größten relativen Abweichung (estimated vs. simulated).
Liest e2e_test_output/deviations_summary.json (nach Lauf von test_predictions_vs_db.py).

Usage (aus DB oder 3_prediction):
  python 3_prediction/show_worst_deviations.py
  python 3_prediction/show_worst_deviations.py --top 30
"""
from pathlib import Path
import json
import argparse

SCRIPT_DIR = Path(__file__).resolve().parent
E2E_OUTPUT_DIR = SCRIPT_DIR / "e2e_test_output"
TARGETS = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]


def main():
    parser = argparse.ArgumentParser(description="Top-N Configs mit größter relativer Abweichung")
    parser.add_argument("--top", type=int, default=30, help="Anzahl Configs (default: 30)")
    parser.add_argument("--json", default=None, help="Pfad zu deviations_summary.json (default: e2e_test_output/deviations_summary.json)")
    args = parser.parse_args()

    path = Path(args.json) if args.json else E2E_OUTPUT_DIR / "deviations_summary.json"
    if not path.exists():
        print(f"Datei nicht gefunden: {path}")
        print("Zuerst E2E-Test ausführen: python 3_prediction/test_predictions_vs_db.py")
        return

    with open(path) as f:
        records = json.load(f)

    # Pro Config: maximale diff_rel_raw_pct über alle Targets
    def max_pct(rec):
        pcts = []
        for t in TARGETS:
            if rec.get(t) and rec[t].get("diff_rel_raw_pct") is not None:
                pcts.append(rec[t]["diff_rel_raw_pct"])
        return max(pcts) if pcts else 0.0

    sorted_records = sorted(records, key=max_pct, reverse=True)[: args.top]

    print(f"Top {args.top} Configs nach maximaler relativer Abweichung (estimated vs. simulated)\n")
    print("=" * 100)

    for i, rec in enumerate(sorted_records, 1):
        cid = rec["config_id"]
        print(f"\n  #{i}  config_id = {cid}")
        for t in TARGETS:
            blk = rec.get(t)
            if not blk:
                continue
            est = blk.get("estimated")
            sim = blk.get("simulated")
            pct = blk.get("diff_rel_raw_pct")
            if pct is None:
                continue
            print(f"       {t}:")
            print(f"         estimated = {est:,.2f}   simulated = {sim:,.2f}   diff_rel = {pct:.1f}%")

    print("\n" + "=" * 100)
    print(f"Quelle: {path}")


if __name__ == "__main__":
    main()
