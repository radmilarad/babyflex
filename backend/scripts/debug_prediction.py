import pandas as pd
import joblib
import sys
import os
import importlib.util
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

def debug():
    print("--- DEBUGGING ML PREDICTION ---")

    # 1. Test Feature Extraction Import
    pred_script = PROJECT_ROOT / "3_prediction" / "calculate_features.py"
    if not pred_script.exists():
        print(f"❌ Script not found: {pred_script}")
        return

    try:
        spec = importlib.util.spec_from_file_location("calc_features", pred_script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print("✅ calculate_features.py imported")
    except Exception as e:
        print(f"❌ Failed to import calculate_features.py: {e}")
        return

    # 2. Mock Data (Simulate what the server sends)
    print("\n--- Generating Mock Data ---")
    mock_df = pd.DataFrame({
        'timestamp_utc': pd.date_range('2024-01-01', periods=100, freq='15min'),
        'grid_load_kwh': [10.0] * 100,
        'consumption_load_kwh': [10.0] * 100,
        'pv_load_kwh': [0.0] * 100
    })

    params = {
        "list_battery_usable_max_state": 100.0,
        "list_battery_num_annual_cycles": 200.0,
        "list_battery_proportion_hourly_max_load": 0.5,
        "pv_peak_power": 50.0,
        "pv_consumed_percentage": 0.8,
        "working_price_eur_per_kwh": 0.20,
        "power_price_eur_per_kw": 100.0,
        "pv_annual_total": 50000.0 # Added this
    }

    # 3. Test Feature Calculation
    try:
        df_ml = module.build_ml_input_df(mock_df)
        col_feats = module.calculate_column_features(df_ml)
        cross_feats = module.calculate_cross_features(df_ml)
        all_feats = {**params, **col_feats, **cross_feats}
        X_df = pd.DataFrame([all_feats])
        print(f"✅ Features calculated: {len(all_feats)} features found")
        # print("Feature keys:", list(all_feats.keys()))
    except Exception as e:
        print(f"❌ Feature calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. Test Model Loading & Prediction
    models_dir = PROJECT_ROOT / "2_ml" / "artifacts" / "models"
    targets = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]

    for target in targets:
        print(f"\nTesting target: {target}")
        files = list(models_dir.glob(f"*{target}*.pkl"))
        if not files:
            print(f"❌ No model file found for {target}")
            continue

        model_path = files[0]
        try:
            model = joblib.load(model_path)
            print(f"✅ Model loaded: {model_path.name}")

            # Check features
            if hasattr(model, "feature_names_in_"):
                missing = set(model.feature_names_in_) - set(X_df.columns)
                if missing:
                    print(f"❌ MISSING FEATURES: {missing}")
                    # Fix X_df for test
                    for c in missing: X_df[c] = 0.0

                # Reorder
                X_ready = X_df[model.feature_names_in_]
            else:
                X_ready = X_df

            pred = model.predict(X_ready)[0]
            print(f"✅ Prediction: {pred}")

        except Exception as e:
            print(f"❌ Model prediction failed: {e}")

if __name__ == "__main__":
    debug()
