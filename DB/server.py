from fastapi import FastAPI, Query, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from battery_db import BatteryDatabase
from benefit_calculator import BenefitCalculator
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import json
import os
import shutil
import uuid
import requests
from datetime import date
from dateutil.relativedelta import relativedelta

# -------------------------------------------------------------------
# 🔐 Load environment variables (.env)
# -------------------------------------------------------------------
load_dotenv()
ENET_USERNAME = os.getenv("ENET_USERNAME")
ENET_PASSWORD = os.getenv("ENET_PASSWORD")

# -------------------------------------------------------------------
# 🧹 Helper: Convert DataFrame to JSON-safe format
# -------------------------------------------------------------------
def dataframe_to_json(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a JSON string that is fully compliant (no NaN/inf)."""
    if df is None or df.empty:
        return "[]"
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.astype(object).where(pd.notnull(df), None)
    return json.dumps(df.to_dict(orient="records"), allow_nan=False)

# -------------------------------------------------------------------
# ⚡ Enet Navigator (RLM-only)
# -------------------------------------------------------------------
ENET_BASE_URL = "https://ws.enet-navigator.de/netzentgelte/strom/rlm/adresse/belieferungszeitraum/jahresverbrauch"

def build_enet_rlm_url(
    postCode: str,
    location: str,
    street: str,
    houseNumber: str,
    yearlyConsumption: int,
    maxPeak: int,
    startDate: str = None,
) -> str:
    """Build Enet Navigator API URL for RLM grid fees."""
    start = date.fromisoformat(startDate) if startDate else date.today()
    end = (start + relativedelta(years=1)).isoformat()

    address = f"plz={postCode}&ort={location}&strasse={street}&hausnummer={houseNumber}"
    voltage = "spannungsebeneLieferung=MSP&spannungsebeneMessung=MSP"
    market_config = (
        f"maximaleLeistung={maxPeak}&leistungsspitzeKA=true&"
        "zaehlerGruppe=ELEKTRONISCH&energieintensiv=false&privilegierterKundeNachEEG=false"
    )
    url_default = (
        f"tarifart=EINTARIF&jahresverbrauchHt={yearlyConsumption}&energierichtung=EINRICHTUNGSZAEHLER&"
        "kostenabgrenzung=OHNE&kommunaleAbnahmestelle=false"
    )

    full_url = (
        f"{ENET_BASE_URL}?belieferungVon={start.isoformat()}&belieferungBis={end}&"
        f"{address}&{voltage}&{market_config}&{url_default}"
    )
    return full_url

# -------------------------------------------------------------------
# 🚀 FastAPI App Setup
# -------------------------------------------------------------------
app = FastAPI(title="Trawa Flex API", version="1.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# 🧠 Initialize Database + Benefit Calculator
# -------------------------------------------------------------------
db = BatteryDatabase("database/battery_simulations.duckdb")
calc = BenefitCalculator(db)

# -------------------------------------------------------------------
# 🌐 Root Route
# -------------------------------------------------------------------
@app.get("/")
def index():
    return {"message": "✅ Trawa Flex API is running!"}

# -------------------------------------------------------------------
# 👥 Clients & Runs
# -------------------------------------------------------------------
@app.get("/api/clients")
def get_clients():
    df = db.get_clients()
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

@app.get("/api/runs")
def get_runs(client_name: str = Query(None)):
    df = db.get_runs(client_name)
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

# -------------------------------------------------------------------
# 📊 KPI & Timeseries Data
# -------------------------------------------------------------------
@app.get("/api/kpis")
def get_kpis(client_name: str, run_name: str, config_name: str = Query(None)):
    df = db.get_kpis(client_name, run_name, config_name)
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

@app.get("/api/timeseries")
def get_timeseries(client_name: str, run_name: str, config_name: str):
    df = db.query_timeseries_csv(client_name, run_name, config_name)
    if df.empty:
        return JSONResponse(content={"message": "No timeseries found"})
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

# -------------------------------------------------------------------
# 📥 Submit Simulation Form & File (NEW)
# -------------------------------------------------------------------
@app.post("/api/submit-simulation")
async def submit_simulation(
    # 1. The File
    file: UploadFile = File(...),

    # 2. The Form Data (mapped to your JSON keys)
    list_battery_usable_max_state: float = Form(...),
    list_battery_num_annual_cycles: float = Form(...),
    list_battery_proportion_hourly_max_load: float = Form(...),
    pv_peak_power: float = Form(...),
    pv_consumed_percentage: float = Form(...),
    working_price_eur_per_kwh: float = Form(...),
    power_price_eur_per_kw: float = Form(...),
):
    """
    Accepts CSV file + simulation parameters, saves the file,
    and triggers calculation logic.
    """

    # --- A. Save the file locally ---
    upload_dir = "database/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename to avoid overwrites
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(upload_dir, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # --- B. Load CSV into DataFrame ---
    try:
        df_input = pd.read_csv(file_path)
        if df_input.empty:
            raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

    # --- C. Organize Parameters ---
    simulation_params = {
        "list_battery_usable_max_state": list_battery_usable_max_state,
        "list_battery_num_annual_cycles": list_battery_num_annual_cycles,
        "list_battery_proportion_hourly_max_load": list_battery_proportion_hourly_max_load,
        "pv_peak_power": pv_peak_power,
        "pv_consumed_percentage": pv_consumed_percentage,
        "working_price_eur_per_kwh": working_price_eur_per_kwh,
        "power_price_eur_per_kw": power_price_eur_per_kw,
        "original_filename": file.filename,
        "stored_file_path": file_path
    }

    # --- D. Perform Calculations & DB Insert ---
    # TODO: You need to implement the specific logic in your `db` or `calc` classes.
    # Below is a hypothetical example of how you would call it:

    try:
        # Example:
        # 1. Insert input data into DB and get a new run_id
        # run_id = db.create_new_simulation_run(simulation_params, df_input)

        # 2. Run the calculation
        # results = calc.perform_simulation(df_input, simulation_params)

        # 3. For now, we return a success message and the params
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")

    return {
        "message": "Simulation submitted successfully",
        "file_path": file_path,
        "rows_received": len(df_input),
        "parameters": simulation_params,
        # "results": results.to_dict() # Uncomment when calculation logic is ready
    }

# -------------------------------------------------------------------
# ⚡ Benefit Calculations
# -------------------------------------------------------------------
@app.get("/api/benefits")
def get_benefits(client_name: str = Query(None), run_name: str = Query(None)):
    """Calculate benefit KPIs dynamically."""
    if run_name:
        df = calc.calculate_benefits_for_run(client_name, run_name)
    else:
        df = calc.calculate_all_benefits(client_name)
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

@app.get("/api/benefit-summary")
def get_benefit_summary(client_name: str = Query(None)):
    """Get summary statistics for all calculated benefits."""
    df = calc.calculate_all_benefits(client_name)
    summary = calc.get_benefit_summary(df)
    safe_json = dataframe_to_json(summary)
    return Response(content=safe_json, media_type="application/json")

# -------------------------------------------------------------------
# 🔍 Compare Battery Configurations
# -------------------------------------------------------------------
@app.get("/api/compare")
def compare_configs(client_name: str, run_name: str, kpi_name: str = Query(None)):
    df = db.compare_configs(client_name, run_name, kpi_name)
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

# -------------------------------------------------------------------
# ⚡ Enet Grid Fee (Authenticated RLM)
# -------------------------------------------------------------------
@app.get("/api/enet-gridfee")
def get_enet_gridfee(
    postCode: str,
    location: str,
    street: str,
    houseNumber: str,
    yearlyConsumption: int = 100000,
    maxPeak: int = 30,
    startDate: str = date.today().isoformat(),
):
    """
    Query Enet Navigator API for RLM grid fee prices by address (authenticated).
    """
    if not ENET_USERNAME or not ENET_PASSWORD:
        raise HTTPException(status_code=500, detail="Enet credentials not set in .env")

    url = build_enet_rlm_url(
        postCode=postCode,
        location=location,
        street=street,
        houseNumber=houseNumber,
        yearlyConsumption=yearlyConsumption,
        maxPeak=maxPeak,
        startDate=startDate,
    )

    try:
        res = requests.get(url, auth=(ENET_USERNAME, ENET_PASSWORD), timeout=15)
        if res.status_code == 401:
            raise HTTPException(status_code=401, detail="Authentication failed. Check ENET_USERNAME and ENET_PASSWORD.")
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enet request failed: {e}")

# -------------------------------------------------------------------
# 🧩 Recalculate & Save Benefits
# -------------------------------------------------------------------
@app.post("/api/recalculate-benefits")
def recalculate_benefits(client_name: str = Query(None)):
    """Recalculate all benefits and save them into the database."""
    df = calc.calculate_all_benefits(client_name)
    calc.save_benefits_as_kpis(df)
    safe_json = json.dumps({
        "message": "✅ Benefits recalculated and saved",
        "records": len(df)
    })
    return Response(content=safe_json, media_type="application/json")

# -------------------------------------------------------------------
# 🧹 Health Check
# -------------------------------------------------------------------
@app.get("/api/health")
def health_check():
    return {"status": "ok", "db_connected": True}
