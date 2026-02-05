#!/usr/bin/env python3
"""
Weitere Ausgaben fürs Frontend in outputs_for_frontend.json schreiben.
=======================================================================

Berechnet aus der preprocessed CSV (frontend_data/load_consumption_*_preprocessed.csv):
- total_grid_load_kwh   – Summe grid_load_kwh (Total Grid Load, kWh)
- pv_generation_kwh    – Summe pv_load_kwh (PV Gen, kWh)
- peak_grid_load_kw    – Max grid_load_kwh × 4 (Peak grid load in kW; ×4 weil 15-min Intervalle)
- usage_hours_h        – total_grid_load_kwh / peak_grid_load_kw (Vollbenutzungsstunden, h)
- estimated_consumption_kwh – Summe consumption (consumption_kwh / consumption_load_kwh)

Außerdem:
- warning_message – Platzhalter; Logik/Abhängigkeit kannst du später angeben.

Bestehende Keys in outputs_for_frontend.json (z.B. peak_shaving_benefit, …) bleiben
erhalten; diese Summary-Werte werden ergänzt bzw. überschrieben.

  python 3_prediction/write_other_outputs.py
  python 3_prediction/write_other_outputs.py --input frontend_data/load_consumption_X_preprocessed.csv --output frontend_data/outputs_for_frontend.json
"""
from pathlib import Path
import argparse
import json

SCRIPT_DIR = Path(__file__).resolve().parent
FRONTEND_DATA = SCRIPT_DIR / "frontend_data"
OUTPUT_JSON = FRONTEND_DATA / "outputs_for_frontend.json"


def find_preprocessed_csv(dir_path: Path) -> Path | None:
    candidates = sorted(dir_path.glob("load_consumption_*_preprocessed.csv"))
    return candidates[0] if candidates else None


def compute_summaries(csv_path: Path) -> dict:
    import pandas as pd
    df = pd.read_csv(csv_path)
    if "grid_load_kwh" not in df.columns:
        raise ValueError(f"CSV braucht Spalte grid_load_kwh. Gefunden: {list(df.columns)}")
    total_grid_load_kwh = float(df["grid_load_kwh"].sum())
    # Peak in kW: kWh × 4 (weil 15-min Intervalle: kWh/0.25h = kW)
    peak_grid_load_kw = float(df["grid_load_kwh"].max()) * 4
    # Usage hours basierend auf peak_grid_load_kw
    usage_hours_h = total_grid_load_kwh / peak_grid_load_kw if peak_grid_load_kw > 0 else None

    pv_col = "pv_load_kwh" if "pv_load_kwh" in df.columns else None
    pv_generation_kwh = float(df[pv_col].sum()) if pv_col else None

    consumption_col = "consumption_kwh" if "consumption_kwh" in df.columns else "consumption_load_kwh"
    estimated_consumption_kwh = float(df[consumption_col].sum()) if consumption_col in df.columns else None

    return {
        "total_grid_load_kwh": round(total_grid_load_kwh, 2),
        "pv_generation_kwh": round(pv_generation_kwh, 2) if pv_generation_kwh is not None else None,
        "peak_grid_load_kw": round(peak_grid_load_kw, 2),
        "usage_hours_h": round(usage_hours_h, 2) if usage_hours_h is not None else None,
        "estimated_consumption_kwh": round(estimated_consumption_kwh, 2) if estimated_consumption_kwh is not None else None,
    }


def generate_warnings(summaries: dict, predictions: dict) -> str:
    """Generiert kurze Warnhinweise basierend auf den Daten."""
    warnings = []
    
    # Verbrauch in GWh
    consumption_kwh = summaries.get("estimated_consumption_kwh") or summaries.get("total_grid_load_kwh") or 0
    consumption_gwh = consumption_kwh / 1_000_000
    
    # Warnung bei großem Verbrauch (> 10 GWh)
    if consumption_gwh > 10:
        warnings.append(
            f"Großverbraucher ({consumption_gwh:.0f} GWh): Schätzung der Netzentgeltreduktion mit höherer Unsicherheit."
        )
    
    # Usage Hours
    usage_hours = summaries.get("usage_hours_h") or 0
    
    # Spitzenlast (< 2000 h)
    if usage_hours > 0 and usage_hours < 2000:
        warnings.append(
            f"Spitzenlastprofil ({usage_hours:.0f} h): Peak-Shaving-Potenzial könnte höher sein."
        )
    
    # Bandlast (> 6000 h)
    if usage_hours > 6000:
        warnings.append(
            f"Bandlastprofil ({usage_hours:.0f} h): Peak-Shaving-Potenzial typischerweise geringer."
        )
    
    return " | ".join(warnings) if warnings else ""


def main():
    parser = argparse.ArgumentParser(description="Summary-Werte + warning_message in outputs_for_frontend.json schreiben")
    parser.add_argument("--input", default=None, help="Preprocessed CSV (default: frontend_data/load_consumption_*_preprocessed.csv)")
    parser.add_argument("--output", default=str(OUTPUT_JSON), help="Ziel-JSON (default: frontend_data/outputs_for_frontend.json)")
    args = parser.parse_args()

    csv_path = Path(args.input) if args.input else find_preprocessed_csv(FRONTEND_DATA)
    if not csv_path or not csv_path.exists():
        raise FileNotFoundError(
            f"Preprocessed CSV nicht gefunden. In {FRONTEND_DATA} ablegen oder --input angeben."
        )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summaries = compute_summaries(csv_path)
    
    # Lade bestehende Predictions (falls vorhanden)
    existing = {}
    if out_path.exists():
        try:
            with open(out_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    
    # Generiere Warnhinweise basierend auf Summaries und Predictions
    warning_message = generate_warnings(summaries, existing)

    merged = {**existing, **summaries, "warning_message": warning_message}
    with open(out_path, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"Summary-Werte + warning_message geschrieben: {out_path}")
    print(f"  total_grid_load_kwh={merged.get('total_grid_load_kwh')}, peak_grid_load_kw={merged.get('peak_grid_load_kw')}, usage_hours_h={merged.get('usage_hours_h')}")
    print(f"  pv_generation_kwh={merged.get('pv_generation_kwh')}, estimated_consumption_kwh={merged.get('estimated_consumption_kwh')}")
    print(f"  warning_message={repr(merged.get('warning_message'))}")


if __name__ == "__main__":
    main()
