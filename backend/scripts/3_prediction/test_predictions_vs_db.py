"""
Tests: Predictions vs. Database / Training Data
==============================================

Validates that the 3_prediction pipeline produces predictions consistent with
the data used for training.

 1) test_feature_columns_match_parquet – Feature-Spalten Registry vs. Parquet.
 2) test_prediction_vs_parquet_feature_matrix – Vorhersage vs. Trainings-Matrix.
 3) test_prediction_vs_db_ml_features – Features aus DB (ml_features) vs. kpi_summary.
 4) test_extensive_e2e_via_scripts – Alle Configs: timeseries_ml → calculate_features
    → predict_buckets, nur deviations_summary.json + worst_deviations.json.

Run: python 3_prediction/test_predictions_vs_db.py
     python -m pytest 3_prediction/test_predictions_vs_db.py -v
"""
from pathlib import Path
import json
import os
import sys

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DB_ROOT = SCRIPT_DIR.parent
if str(DB_ROOT) not in sys.path:
    sys.path.insert(0, str(DB_ROOT))

TARGETS = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]
TARGET_COLS = [f"target_{t}" for t in TARGETS]

MODELS_3P = SCRIPT_DIR / "models"
MODELS_2ML = DB_ROOT / "2_ml" / "artifacts" / "models"
FEATURES_2ML = DB_ROOT / "2_ml" / "artifacts" / "features" / "feature_matrix.parquet"
DB_PATH = DB_ROOT / "database" / "battery_simulations.duckdb"
E2E_OUTPUT_DIR = SCRIPT_DIR / "e2e_test_output"


def _get_models_dir():
    if (MODELS_3P / "registry.json").exists():
        return MODELS_3P
    return MODELS_2ML


def _load_registry():
    models_dir = _get_models_dir()
    with open(models_dir / "registry.json", "r") as f:
        return json.load(f)


def _get_feature_columns(registry):
    for name in TARGETS:
        if name in registry and "feature_importance" in registry[name]:
            return list(registry[name]["feature_importance"].keys())
    return []


def _load_models():
    import joblib
    models_dir = _get_models_dir()
    out = {}
    for t in TARGETS:
        path = models_dir / f"{t}_model.joblib"
        if path.exists():
            out[t] = joblib.load(path)
    return out


# -----------------------------------------------------------------------------
# 1) Feature-Spalten: Registry vs. Parquet
# -----------------------------------------------------------------------------
def test_feature_columns_match_parquet():
    registry = _load_registry()
    feature_cols = _get_feature_columns(registry)
    if not FEATURES_2ML.exists():
        raise FileNotFoundError(f"Feature matrix not found: {FEATURES_2ML}")
    df = pd.read_parquet(FEATURES_2ML)
    exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
    parquet_feature_cols = [c for c in df.columns if not c.startswith("target_") and c not in exclude]
    if set(parquet_feature_cols) != set(feature_cols):
        missing = set(feature_cols) - set(parquet_feature_cols)
        extra = set(parquet_feature_cols) - set(feature_cols)
        raise AssertionError(f"Feature columns mismatch. In registry not in parquet: {missing}. In parquet not in registry: {extra}")


# -----------------------------------------------------------------------------
# 2) Vorhersage vs. Parquet Feature-Matrix
# -----------------------------------------------------------------------------
def test_prediction_vs_parquet_feature_matrix():
    if not FEATURES_2ML.exists():
        raise FileNotFoundError(f"Feature matrix not found: {FEATURES_2ML}")
    registry = _load_registry()
    feature_cols = _get_feature_columns(registry)
    df = pd.read_parquet(FEATURES_2ML)
    for c in TARGET_COLS:
        if c not in df.columns:
            raise AssertionError(f"Target column {c} not in parquet")
    valid = df.dropna(subset=TARGET_COLS, how="any")
    if valid.empty:
        return
    X = valid[feature_cols].copy()
    for c in feature_cols:
        if c in X.columns and X[c].isna().any():
            X[c] = X[c].fillna(X[c].median())
    X = X.fillna(0)
    models = _load_models()
    errors = []
    for _, row in valid.iterrows():
        X_row = pd.DataFrame([row[feature_cols].values], columns=feature_cols)
        for target, target_col in zip(TARGETS, TARGET_COLS):
            if target not in models or target_col not in row:
                continue
            pred = models[target].predict(X_row)[0]
            actual = row[target_col]
            if pd.notna(actual):
                errors.append((target, abs(pred - actual)))
    if not errors:
        return
    by_target = {}
    for t, e in errors:
        by_target.setdefault(t, []).append(e)
    for target, errs in by_target.items():
        mae = np.mean(errs)
        train_mae = registry.get(target, {}).get("mae")
        if train_mae is not None and train_mae > 0:
            assert mae <= 2.5 * train_mae, (
                f"{target}: MAE vs parquet {mae:.0f} > 2.5 * train MAE ({train_mae:.0f})"
            )


# -----------------------------------------------------------------------------
# 3) Vorhersage vs. DB (ml_features + kpi_summary)
# -----------------------------------------------------------------------------
DIRECT_INPUT_NAMES = [
    "list_battery_usable_max_state",
    "list_battery_num_annual_cycles",
    "list_battery_proportion_hourly_max_load",
    "pv_annual_total",
    "pv_consumed_percentage",
    "static_grid_fees",
    "grid_fee_max_load_peak",
]


def test_prediction_vs_db_ml_features():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    try:
        import duckdb
    except ImportError:
        import pytest
        pytest.skip("duckdb not installed")
    registry = _load_registry()
    feature_cols = _get_feature_columns(registry)
    models = _load_models()
    parquet_df = pd.read_parquet(FEATURES_2ML) if FEATURES_2ML.exists() else None
    medians = parquet_df[feature_cols].median().to_dict() if parquet_df is not None and all(c in parquet_df.columns for c in feature_cols) else {}

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    fs_name = "default"
    mf = conn.execute("""
        SELECT config_id, features FROM ml_features mf
        JOIN feature_sets fs ON mf.feature_set_id = fs.feature_set_id
        WHERE fs.feature_set_name = ?
    """, [fs_name]).df()
    kpi = conn.execute("""
        SELECT config_id, kpi_name, kpi_value FROM kpi_summary
        WHERE kpi_name IN ('peak_shaving_benefit', 'energy_procurement_optimization', 'trading_revenue')
    """).df()
    conn.close()

    if mf.empty or kpi.empty:
        return
    kpi_pivot = kpi.pivot(index="config_id", columns="kpi_name", values="kpi_value")
    merged = mf.merge(kpi_pivot, left_on="config_id", right_index=True, how="inner")
    for t, target_col in zip(TARGETS, TARGET_COLS):
        if t in merged.columns and target_col not in merged.columns:
            merged[target_col] = merged[t]
    valid = merged.dropna(subset=TARGET_COLS, how="any")
    if valid.empty:
        return
    sample = valid.sample(n=min(100, len(valid)), random_state=42)

    def _impute_val(col, v):
        med = medians.get(col)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        return float(med) if med is not None and not (isinstance(med, float) and np.isnan(med)) else 0.0

    errors = []
    for _, r in sample.iterrows():
        feats = r["features"] if isinstance(r["features"], dict) else json.loads(r["features"])
        row_vals = [_impute_val(col, feats.get(col)) for col in feature_cols]
        X_row = pd.DataFrame([row_vals], columns=feature_cols)
        for target, target_col in zip(TARGETS, TARGET_COLS):
            if target not in models or target_col not in r:
                continue
            pred = models[target].predict(X_row)[0]
            actual = r[target_col]
            if pd.notna(actual):
                errors.append((target, abs(pred - actual)))
    if not errors:
        return
    by_target = {}
    for t, e in errors:
        by_target.setdefault(t, []).append(e)
    for target, errs in by_target.items():
        mae = np.mean(errs)
        train_mae = registry.get(target, {}).get("mae")
        if train_mae is not None and train_mae > 0:
            assert mae <= 2.5 * train_mae, (
                f"{target}: MAE vs DB {mae:.0f} > 2.5 * train MAE ({train_mae:.0f})"
            )


# -----------------------------------------------------------------------------
# 4) E2E: Alle Configs, nur deviations_summary + worst_deviations
# -----------------------------------------------------------------------------
def test_extensive_e2e_via_scripts():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    try:
        import duckdb
    except ImportError:
        import pytest
        pytest.skip("duckdb not installed")
    import subprocess
    import tempfile

    E2E_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = _load_registry()
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    kpi_names = list(DIRECT_INPUT_NAMES) + ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]
    placeholders = ",".join(["?"] * len(kpi_names))
    configs_with_kpis = conn.execute(f"""
        SELECT config_id, kpi_name, kpi_value
        FROM kpi_summary
        WHERE kpi_name IN ({placeholders})
    """, kpi_names).df()
    config_ids_with_ts = conn.execute("SELECT DISTINCT config_id FROM timeseries_ml").df()["config_id"].tolist()
    conn.close()

    if configs_with_kpis.empty:
        raise AssertionError("No rows in kpi_summary for direct inputs + targets.")
    pivot = configs_with_kpis.pivot(index="config_id", columns="kpi_name", values="kpi_value")
    for c in ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]:
        if c in pivot.columns:
            pivot = pivot.dropna(subset=[c], how="any")
    pivot = pivot.loc[pivot.index.isin(config_ids_with_ts)]
    if pivot.empty:
        raise AssertionError("No configs with all direct inputs, 3 targets, and rows in timeseries_ml.")

    chosen = pivot.index.tolist()
    n_total = len(chosen)
    print(f"E2E: {n_total} Configs zu testen (geschätzt ~5–20 s pro Config).")
    with open(E2E_OUTPUT_DIR / "progress.json", "w") as f:
        json.dump({"n_total": n_total, "n_done": 0}, f)

    errors_by_target = {t: [] for t in TARGETS}
    deviations_records = []
    script_dir_3p = SCRIPT_DIR
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    MAX_REL_DEVIATION = 2.0

    for idx, config_id in enumerate(chosen):
        row = pivot.loc[config_id]
        df_ts = conn.execute("""
            SELECT timestamp_utc, grid_load_kwh, consumption_load_kwh, pv_load_kwh
            FROM timeseries_ml WHERE config_id = ? ORDER BY timestamp_utc
        """, [int(config_id)]).df()
        if df_ts.empty or len(df_ts) < 2:
            continue
        frontend_data = {k: (float(row[k]) if pd.notna(row.get(k)) and row.get(k) is not None else None) for k in DIRECT_INPUT_NAMES}
        with tempfile.TemporaryDirectory(prefix="e2e_3p_") as tmp:
            tmp = Path(tmp)
            (tmp / "frontend_data").mkdir(parents=True)
            (tmp / "working_data").mkdir(parents=True)
            with open(tmp / "frontend_data" / "frontend_data.json", "w") as f:
                json.dump(frontend_data, f, indent=2)
            preprocessed = tmp / "preprocessed.csv"
            df_ts.to_csv(preprocessed, index=False)
            feat_out = tmp / "working_data" / "features.json"
            out_json = tmp / "outputs.json"
            res = subprocess.run([
                sys.executable, str(script_dir_3p / "calculate_features.py"),
                "--input", str(preprocessed), "--inputs", str(tmp / "frontend_data" / "frontend_data.json"),
                "--output", str(feat_out),
            ], cwd=str(DB_ROOT), capture_output=True, text=True, timeout=120)
            if res.returncode != 0 or not feat_out.exists():
                continue
            res2 = subprocess.run([
                sys.executable, str(script_dir_3p / "predict_buckets.py"),
                "--features", str(feat_out), "--output", str(out_json),
            ], cwd=str(DB_ROOT), capture_output=True, text=True, timeout=30)
            if res2.returncode != 0 or not out_json.exists():
                continue
            with open(out_json) as f:
                preds = json.load(f)
            rec = {"config_id": int(config_id)}
            for target in TARGETS:
                actual = row.get(target)
                est = preds.get(target)
                if pd.notna(actual) and est is not None:
                    sim = float(actual)
                    diff_abs = abs(est - sim)
                    errors_by_target[target].append(diff_abs)
                    denom = abs(sim) if sim != 0 else None
                    diff_rel_raw = (diff_abs / denom) if denom is not None else None
                    diff_rel_capped = min(diff_rel_raw, MAX_REL_DEVIATION) if diff_rel_raw is not None else None
                    rec[target] = {
                        "estimated": float(est),
                        "simulated": sim,
                        "diff_abs": round(diff_abs, 4),
                        "diff_rel": round(diff_rel_capped, 6) if diff_rel_capped is not None else None,
                        "diff_rel_raw_pct": round(diff_rel_raw * 100, 2) if diff_rel_raw is not None else None,
                    }
                else:
                    rec[target] = None
            deviations_records.append(rec)

        step = 50 if n_total > 100 else 10
        if (idx + 1) % step == 0 or idx == 0 or idx == n_total - 1:
            with open(E2E_OUTPUT_DIR / "progress.json", "w") as f:
                json.dump({"n_total": n_total, "n_done": len(deviations_records)}, f)
            with open(E2E_OUTPUT_DIR / "deviations_summary.json", "w") as f:
                json.dump(deviations_records, f, indent=2)
            pct = 100 * (idx + 1) / n_total
            print(f"  E2E progress: {idx + 1}/{n_total} Configs ({pct:.1f}%) – {len(deviations_records)} mit Ergebnis")

    conn.close()
    with open(E2E_OUTPUT_DIR / "deviations_summary.json", "w") as f:
        json.dump(deviations_records, f, indent=2)
    with open(E2E_OUTPUT_DIR / "progress.json", "w") as f:
        json.dump({"n_total": n_total, "n_done": len(deviations_records)}, f)

    MAX_REL_PCT = 200.0
    violations = []
    for rec in deviations_records:
        for t in TARGETS:
            if rec.get(t) and rec[t].get("diff_rel_raw_pct") is not None and rec[t]["diff_rel_raw_pct"] > MAX_REL_PCT:
                violations.append((int(rec["config_id"]), t, rec[t]["diff_rel_raw_pct"], rec[t]["estimated"], rec[t]["simulated"]))

    def _max_raw_pct(rec):
        pcts = [rec[t]["diff_rel_raw_pct"] for t in TARGETS if rec.get(t) and rec[t].get("diff_rel_raw_pct") is not None]
        return max(pcts) if pcts else 0.0
    worst = sorted(deviations_records, key=_max_raw_pct, reverse=True)[:20]
    with open(E2E_OUTPUT_DIR / "worst_deviations.json", "w") as f:
        json.dump(worst, f, indent=2)

    rel_by_target = {t: [] for t in TARGETS}
    for rec in deviations_records:
        for t in TARGETS:
            if rec.get(t) and rec[t].get("diff_rel") is not None:
                rel_by_target[t].append(rec[t]["diff_rel"] * 100)
    for target in TARGETS:
        vals = rel_by_target[target]
        n_viol = sum(1 for v in violations if v[1] == target)
        if vals:
            arr = np.array(vals)
            print(f"  {target}: n={len(arr)}  avg={np.mean(arr):.2f}%  min={np.min(arr):.2f}%  max={np.max(arr):.2f}%  std={np.std(arr):.2f}%  violations >{MAX_REL_PCT:.0f}%: {n_viol}")

    if violations:
        lines = [f"  config_id={c} target={t} diff_rel_raw_pct={pct:.1f}% estimated={est} simulated={sim}" for c, t, pct, est, sim in violations[:15]]
        if len(violations) > 15:
            lines.append(f"  ... und {len(violations) - 15} weitere")
        raise AssertionError(f"Relative Abweichung >{MAX_REL_PCT:.0f}% nicht erlaubt ({len(violations)} Verstöße).\n" + "\n".join(lines))

    for target in TARGETS:
        errs = errors_by_target[target]
        if not errs:
            continue
        mae = np.mean(errs)
        train_mae = registry.get(target, {}).get("mae")
        if train_mae is not None and train_mae > 0:
            assert mae <= 2.5 * train_mae, (
                f"{target}: E2E MAE {mae:.0f} (n={len(errs)}) > 2.5 * train MAE ({train_mae:.0f})"
            )


if __name__ == "__main__":
    import traceback
    print("DB root:", DB_ROOT)
    print("Feature matrix:", FEATURES_2ML, "exists:", FEATURES_2ML.exists())
    print("Models dir:", _get_models_dir())
    print()
    ran, failed = 0, []
    for name, fn in [
        ("feature_columns_match_parquet", test_feature_columns_match_parquet),
        ("prediction_vs_parquet_feature_matrix", test_prediction_vs_parquet_feature_matrix),
        ("prediction_vs_db_ml_features", test_prediction_vs_db_ml_features),
        ("extensive_e2e_via_scripts", test_extensive_e2e_via_scripts),
    ]:
        print(f"--- {name} ---")
        try:
            fn()
            print("  OK")
            ran += 1
        except Exception as e:
            print("  FAIL:", e)
            traceback.print_exc()
            failed.append(name)
        print()
    print("Done:", ran, "passed", len(failed), "failed")
    if failed:
        print("Failed:", failed)
        sys.exit(1)
