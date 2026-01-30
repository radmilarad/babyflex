from fastapi import FastAPI, Query, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from battery_db import BatteryDatabase
from dotenv import load_dotenv
import pandas as pd
import os
import shutil
import uuid
import joblib
import requests
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# -------------------------------------------------------------------
# 🔐 Load environment variables
# -------------------------------------------------------------------
load_dotenv()
ENET_USERNAME = os.getenv("ENET_USERNAME")
ENET_PASSWORD = os.getenv("ENET_PASSWORD")

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

    def extract_features(self, df_timeseries: pd.DataFrame, params: dict) -> pd.DataFrame:
        """Extract features matching training data requirements."""
        if 'timestamp_utc' in df_timeseries.columns:
            df_timeseries['timestamp_utc'] = pd.to_datetime(df_timeseries['timestamp_utc'])
            df_timeseries.set_index('timestamp_utc', inplace=True)

        load = df_timeseries.iloc[:, 0] if 'value' not in df_timeseries.columns else df_timeseries['value']

        # Mapped features to match what ML model expects
        features = {
            "ts__load__mean": load.mean(),
            "ts__load__std": load.std(),
            "ts__load__min": load.min(),
            "ts__load__max": load.max(),
            "ts__load__q95": load.quantile(0.95),
            "ts__load__q05": load.quantile(0.05),

            # Direct Inputs
            "list_battery_usable_max_state": float(params.get("list_battery_usable_max_state", 0)),
            "list_battery_num_annual_cycles": float(params.get("list_battery_num_annual_cycles", 0)),
            "list_battery_proportion_hourly_max_load": float(params.get("list_battery_proportion_hourly_max_load", 0)),
            "pv_peak_power": float(params.get("pv_peak_power", 0)),
            "pv_consumed_percentage": float(params.get("pv_consumed_percentage", 0)),

            # NEW PARAMETER NAMES -> Mapped to what ML likely expects (check your feature_extractors.py!)
            # Assuming ML expects 'working_price_eur_per_kwh' but we receive 'static_grid_fees'
            "working_price_eur_per_kwh": float(params.get("static_grid_fees", 0)),
            "power_price_eur_per_kw": float(params.get("grid_fee_max_load_peak", 0)),
        }
        return pd.DataFrame([features])

    def predict(self, df_timeseries: pd.DataFrame, params: dict) -> dict:
        if not self.models:
            return {}

        X_input = self.extract_features(df_timeseries, params)
        results = {}

        for target, model in self.models.items():
            try:
                # Handle feature ordering/missing columns if model supports it
                if hasattr(model, "feature_names_in_"):
                    for col in model.feature_names_in_:
                        if col not in X_input.columns:
                            X_input[col] = 0.0 # Fill missing with 0
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
def get_enet_gridfee(postCode: str, location: str, street: str, houseNumber: str, yearlyConsumption: int = 100000, maxPeak: int = 30, startDate: str = date.today().isoformat()):
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
    # UPDATED PARAMETER NAMES
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
        "static_grid_fees": static_grid_fees,
        "grid_fee_max_load_peak": grid_fee_max_load_peak,
    }

    # 4. Predict
    try:
        results = ml_predictor.predict(df_input, params)

        # Fallback if no ML results (e.g. models missing)
        if not results:
            print("⚠️ No ML results, using fallback math.")
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
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")

    return {
        "message": "Success",
        "run_id": run_name,
        "results": results
    }
