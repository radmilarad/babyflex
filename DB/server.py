from fastapi import FastAPI, Query, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from battery_db import BatteryDatabase
from dotenv import load_dotenv
import pandas as pd
import os
import shutil
import uuid
import json
import requests
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

# -------------------------------------------------------------------
# 🔐 Load environment variables
# -------------------------------------------------------------------
load_dotenv()
ENET_USERNAME = os.getenv("ENET_USERNAME")
ENET_PASSWORD = os.getenv("ENET_PASSWORD")

# -------------------------------------------------------------------
# 📂 Paths
# -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
PREDICTION_DIR = PROJECT_ROOT / "3_prediction"
FRONTEND_DATA_DIR = PREDICTION_DIR / "frontend_data"
OUTPUT_JSON_PATH = FRONTEND_DATA_DIR / "outputs_for_frontend.json"

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

# -------------------------------------------------------------------
# 🌐 Routes
# -------------------------------------------------------------------
@app.get("/")
def index():
    return {"message": "✅ Trawa Flex API is running!"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "db": "connected"}

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

    # 2. Organize Parameters
    params = {
        "list_battery_usable_max_state": list_battery_usable_max_state,
        "list_battery_num_annual_cycles": list_battery_num_annual_cycles,
        "list_battery_proportion_hourly_max_load": list_battery_proportion_hourly_max_load,
        "pv_peak_power": pv_peak_power,
        "pv_consumed_percentage": pv_consumed_percentage,
        "working_price_eur_per_kwh": static_grid_fees,
        "power_price_eur_per_kw": grid_fee_max_load_peak,
    }

    # 3. Read Results from JSON File
    results = {}
    try:
        if OUTPUT_JSON_PATH.exists():
            print(f"📖 Reading results from: {OUTPUT_JSON_PATH}")
            with open(OUTPUT_JSON_PATH, "r") as f:
                results = json.load(f)
        else:
            print(f"⚠️ Warning: Output file not found at {OUTPUT_JSON_PATH}")
            # Fallback if file is missing (so app doesn't crash)
            results = {
                "peak_shaving_benefit": 0,
                "energy_procurement_optimization": 0,
                "trading_revenue": 0
            }
    except Exception as e:
        print(f"❌ Error reading output JSON: {e}")
        results = {"error": "Could not read results file"}

    # 4. Save Run to DB
    try:
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
        print(f"⚠️ DB Save failed (non-critical): {e}")

    return {
        "message": "Success",
        "run_id": run_name,
        "results": results
    }
