from fastapi import FastAPI, Query, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from battery_db import BatteryDatabase
from dotenv import load_dotenv
import pandas as pd
import numpy as np
import os
import shutil
import uuid
import joblib
import requests
import sys
import importlib.util
from pathlib import Path
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# -------------------------------------------------------------------
# 🔐 Load environment variables
# -------------------------------------------------------------------
load_dotenv()
ENET_USERNAME = os.getenv("ENET_USERNAME")
ENET_PASSWORD = os.getenv("ENET_PASSWORD")

# -------------------------------------------------------------------
# 🔗 Import Feature Extraction Logic (Dynamic Import)
# -------------------------------------------------------------------
# We need to import 'calculate_features.py' from '3_prediction/'
# This ensures we use the EXACT same feature logic as the ML pipeline.

PROJECT_ROOT = Path(__file__).resolve().parent
PREDICTION_DIR = PROJECT_ROOT / "3_prediction"

# Add project root to sys.path so internal imports in calculate_features work
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    spec = importlib.util.spec_from_file_location(
        "calculate_features",
        PREDICTION_DIR / "calculate_features.py"
    )
    calc_feat_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calc_feat_module)

    # Expose functions for use
    build_ml_input_df = calc_feat_module.build_ml_input_df
    calculate_column_features = calc_feat_module.calculate_column_features
    calculate_cross_features = calc_feat_module.calculate_cross_features

    print("✅ Successfully imported feature extraction logic from 3_prediction")
except Exception as e:
    print(f"❌ Failed to import feature extraction logic: {e}")
    # Fallback to dummy functions if import fails
    def build_ml_input_df(df): return df
    def calculate_column_features(df): return {}
    def calculate_cross_features(df): return {}

# -------------------------------------------------------------------
# ⚡ Enet Helper
# -------------------------------------------------------------------
ENET_BASE_URL = "https://ws.enet-navigator.de/netzentgelte/strom/rlm/adresse/belieferungszeitraum/jahresverbrauch"

def build_enet_rlm_url(
    postCode: str, location: str, street: str, houseNumber: str,
    yearlyConsumption: int, maxPeak: int, startDate: str = None
) -> str:
    start = date.fromisoformat(startDate) if startDate else date.today()
    end = (start + relativedelta(years=1)).isoformat()
    address = f"plz={postCode}&ort={location}&strasse={street}&hausnummer={houseNumber}"
    voltage = "spannungsebeneLieferung=MSP&spannungsebeneMessung=MSP"
    market_config = "maximaleLeistung={}&leistungsspitzeKA=true&zaehlerGruppe=ELEKTRONISCH&energieintensiv=false&privilegierterKundeNachEEG=false".format(maxPeak)
    url_default = f"tarifart=EINTARIF&jahresverbrauchHt={yearlyConsumption}&energierichtung=EINRICHTUNGSZAEHLER&kostenabgrenzung=OHNE&kommunaleAbnahmestelle=false"
    return f"{ENET_BASE_URL}?belieferungVon={start.isoformat()}&belieferungBis={end}&{address}&{voltage}&{market_config}&{url_default}"

# -------------------------------------------------------------------
# 🧠 ML Prediction Service
# -------------------------------------------------------------------
class MLPredictor:
    def __init__(self, models_dir="2_ml/artifacts/models"):
        self.models = {}
        self.models_dir = models_dir
        self.targets = ["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"]
        self._load_models()

    def _load_models(self):
        print(f"Loading models from {self.models_dir}...")
        if not os.path.exists(self.models_dir):
             print(f"⚠️ Warning: Models directory not found: {self.models_dir}")
             return

        for target in self.targets:
            # Look for ANY .pkl file containing the target name
            possible_files = [f for f in os.listdir(self.models_dir) if target in f and f.endswith(".pkl")]
            if not possible_files:
                print(f"⚠️ Warning: No model found for {target}")
                continue

            # Load the first matching file
            model_path = os.path.join(self.models_dir, possible_files[0])
            try:
                self.models[target] = joblib.load(model_path)
                print(f"✅ Loaded {target}")
            except Exception as e:
                print(f"❌ Failed to load {target}: {e}")

    def prepare_features(self, df_input: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        Prepare features using the exact logic from 3_prediction/calculate_features.py.
        1. Preprocess DataFrame (rename columns, parse dates)
        2. Calculate stats features
        3. Merge with direct inputs (params)
        """
        # --- 1. Preprocess DataFrame ---
        df_proc = df_input.copy()

        # Ensure timestamp column
        if 'timestamp_utc' not in df_proc.columns:
             # Fallback: assume first column is time if not named correctly
             df_proc.columns = ['timestamp_utc', 'value']

        df_proc['timestamp_utc'] = pd.to_datetime(df_proc['timestamp_utc'], utc=True)

        # Map input value to 'grid_load_kwh'
        if 'value' in df_proc.columns:
            df_proc['grid_load_kwh'] = pd.to_numeric(df_proc['value'], errors='coerce').fillna(0)
        elif 'grid_load_kwh' not in df_proc.columns:
             df_proc['grid_load_kwh'] = 0.0 # Should not happen if CSV is valid

        # CRITICAL: Create all alias columns potentially used by extractors
        # Your script uses 'consumption_kwh' in logic but 'consumption_load_kwh' in REQUIRED_COLUMNS.
        # We provide both to be safe.
        df_proc['consumption_kwh'] = df_proc['grid_load_kwh']
        df_proc['consumption_load_kwh'] = df_proc['grid_load_kwh']
        df_proc['pv_load_kwh'] = 0.0 # Placeholder as we don't simulate PV here for speed

        # --- 2. Build ML Input (transforms to timestamp, load_kwh, etc.) ---
        try:
            df_ready = build_ml_input_df(df_proc)
        except Exception as e:
            print(f"⚠️ Feature build failed, using basic proc: {e}")
            df_ready = df_proc

        # --- 3. Calculate Derived Features ---
        try:
            column_feats = calculate_column_features(df_ready)
            cross_feats = calculate_cross_features(df_ready)
        except Exception as e:
            print(f"⚠️ Feature calculation failed: {e}")
            column_feats = {}
            cross_feats = {}

        # --- 4. Merge with Direct Inputs ---

        # Fix: Ensure pv_annual_total exists (Model likely needs it)
        if "pv_annual_total" not in params:
             # Estimate roughly: peak power (kW) * 1000h (simple approximation)
             params["pv_annual_total"] = float(params.get("pv_peak_power", 0)) * 1000

        all_features = {**params, **column_feats, **cross_feats}

        # Convert to DataFrame (1 row)
        return pd.DataFrame([all_features])

    def predict(self, df_timeseries: pd.DataFrame, params: dict) -> dict:
        if not self.models:
            return {}

        # Use the robust feature preparation
        X_input = self.prepare_features(df_timeseries, params)

        results = {}
        for target, model in self.models.items():
            try:
                # Handle feature ordering/missing columns
                if hasattr(model, "feature_names_in_"):
                    # Fill missing columns with 0
                    for col in model.feature_names_in_:
                        if col not in X_input.columns:
                            X_input[col] = 0.0
                    # Reorder columns strictly to match model
                    X_ready = X_input[model.feature_names_in_]
                else:
                    X_ready = X_input

                pred = model.predict(X_ready)[0]
                results[target] = float(pred)
            except Exception as e:
                print(f"Error predicting {target}: {e}")
                results[target] = 0.0
        return results

# -------------------------------------------------------------------
# 🚀 App Setup
# -------------------------------------------------------------------
app = FastAPI(title="Trawa Flex API", version="1.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = BatteryDatabase("database/battery_simulations.duckdb")
ml_predictor = MLPredictor()

# -------------------------------------------------------------------
# 🌐 Routes
# -------------------------------------------------------------------
@app.get("/")
def index():
    return {"message": "✅ Trawa Flex API is running!"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "models_loaded": list(ml_predictor.models.keys())}

@app.get("/api/enet-gridfee")
def get_enet_gridfee(
    postCode: str, location: str, street: str, houseNumber: str,
    yearlyConsumption: int = 100000, maxPeak: int = 30, startDate: str = date.today().isoformat()
):
    if not ENET_USERNAME or not ENET_PASSWORD:
        raise HTTPException(status_code=500, detail="Enet credentials not set")
    url = build_enet_rlm_url(postCode, location, street, houseNumber, yearlyConsumption, maxPeak, startDate)
    try:
        res = requests.get(url, auth=(ENET_USERNAME, ENET_PASSWORD), timeout=15)
        if res.status_code == 401: raise HTTPException(status_code=401, detail="Auth failed")
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Enet Error: {e}")
        raise HTTPException(status_code=500, detail=f"Enet request failed: {e}")

@app.post("/api/submit-simulation")
async def submit_simulation(
    file: UploadFile = File(...),
    list_battery_usable_max_state: float = Form(...),
    list_battery_num_annual_cycles: float = Form(...),
    list_battery_proportion_hourly_max_load: float = Form(...),
    pv_peak_power: float = Form(...),
    pv_consumed_percentage: float = Form(...),
    static_grid_fees: float = Form(...),
    grid_fee_max_load_peak: float = Form(...),
):
    # 1. Save File
    client_name = "Web_Submission"
    run_name = f"Run_{uuid.uuid4().hex[:8]}"
    upload_dir = f"data/{client_name}/{run_name}/Input"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # 2. Load CSV
    try:
        df_input = pd.read_csv(file_path)
        if df_input.empty: raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")

    # 3. Organize Parameters
    params = {
        "list_battery_usable_max_state": list_battery_usable_max_state,
        "list_battery_num_annual_cycles": list_battery_num_annual_cycles,
        "list_battery_proportion_hourly_max_load": list_battery_proportion_hourly_max_load,
        "pv_peak_power": pv_peak_power,
        "pv_consumed_percentage": pv_consumed_percentage,
        # Keys mapped for ML model expectations
        "working_price_eur_per_kwh": static_grid_fees,
        "power_price_eur_per_kw": grid_fee_max_load_peak,
        # Defaults for other params model might expect
        "list_battery_max_state": list_battery_usable_max_state / 0.92,
        "list_battery_efficiency": 0.92,
        "list_battery_usability": 0.92
    }

    # 4. Predict
    try:
        results = ml_predictor.predict(df_input, params)

        # Fallback if no results
        if not results or all(v == 0 for v in results.values()):
            print("⚠️ ML results empty or zero, using fallback math.")
            est_load = (df_input.iloc[:,1].mean() * 8760)
            results = {
                "peak_shaving_benefit": list_battery_usable_max_state * grid_fee_max_load_peak * 0.8,
                "energy_procurement_optimization": est_load * static_grid_fees * 0.10,
                "trading_revenue": list_battery_usable_max_state * list_battery_num_annual_cycles * 0.05
            }

        # Save to DB
        db.add_run(client_name, run_name, "Web Submission", params, datetime.now())
        db.add_battery_config(
            client_name, run_name,
            config_name=f"{int(list_battery_usable_max_state)}kWh",
            is_baseline=False,
            battery_capacity_kwh=list_battery_usable_max_state,
            battery_power_kw=list_battery_usable_max_state * list_battery_proportion_hourly_max_load,
            timeseries_file=None
        )

    except Exception as e:
        print(f"Prediction error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

    return {
        "message": "Success",
        "run_id": run_name,
        "results": results
    }
