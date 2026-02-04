from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

import pandas as pd
import os
import shutil
import uuid
import json
import subprocess
import sys
import requests
import asyncio

from pathlib import Path
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# -------------------------------------------------------------------
# 🛠️ Fix Imports & Paths
# -------------------------------------------------------------------
# This file is in: backend/app/main.py
# We want the root: backend/
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Add 'backend' to python path so we can import the 'scripts' folder
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

# Import from the scripts folder
try:
    from scripts.battery_db import BatteryDatabase
except ImportError as e:
    print(f"❌ Error importing BatteryDatabase: {e}")
    print(f"ℹ️  Python Path is: {sys.path}")
    raise e

# Define Paths relative to Backend Root
PREDICTION_DIR = BACKEND_ROOT / "scripts" / "3_prediction"
FRONTEND_DATA_DIR = PREDICTION_DIR / "frontend_data"
INPUT_JSON_PATH = FRONTEND_DATA_DIR / "frontend_data.json"
OUTPUT_JSON_PATH = FRONTEND_DATA_DIR / "outputs_for_frontend.json"
DB_FILE_PATH = BACKEND_ROOT / "scripts" / "database" / "battery_simulations.duckdb"

# Pipeline intermediate files used by your scripts
PREPROCESSED_CSV_PATH = FRONTEND_DATA_DIR / "input_load_preprocessed.csv"
WORKING_FEATURES_PATH = PREDICTION_DIR / "working_data" / "features.json"

# Ensure dirs exist
FRONTEND_DATA_DIR.mkdir(parents=True, exist_ok=True)
(PREDICTION_DIR / "working_data").mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------
# 🔐 Load environment variables
# -------------------------------------------------------------------
env_path = BACKEND_ROOT / ".env"
load_dotenv(env_path)

ENET_USERNAME = os.getenv("ENET_USERNAME")
ENET_PASSWORD = os.getenv("ENET_PASSWORD")

if not ENET_USERNAME:
    print(f"⚠️ Warning: ENET_USERNAME not found. Checked path: {env_path}")

# -------------------------------------------------------------------
# ⚡ Enet Helper
# -------------------------------------------------------------------
ENET_BASE_URL = "https://ws.enet-navigator.de/netzentgelte/strom/rlm/adresse/belieferungszeitraum/jahresverbrauch"


def build_enet_rlm_url(
    postCode,
    location,
    street,
    houseNumber,
    yearlyConsumption,
    maxPeak,
    startDate=None,
):
    start = date.fromisoformat(startDate) if startDate else date.today()
    end = (start + relativedelta(years=1)).isoformat()
    return (
        f"{ENET_BASE_URL}"
        f"?belieferungVon={start.isoformat()}&belieferungBis={end}"
        f"&plz={postCode}&ort={location}&strasse={street}&hausnummer={houseNumber}"
        f"&spannungsebeneLieferung=MSP&spannungsebeneMessung=MSP"
        f"&maximaleLeistung={maxPeak}&leistungsspitzeKA=true"
        f"&zaehlerGruppe=ELEKTRONISCH&energieintensiv=false"
        f"&privilegierterKundeNachEEG=false&tarifart=EINTARIF"
        f"&jahresverbrauchHt={yearlyConsumption}"
        f"&energierichtung=EINRICHTUNGSZAEHLER&kostenabgrenzung=OHNE"
        f"&kommunaleAbnahmestelle=false"
    )


# -------------------------------------------------------------------
# 🚀 App Setup
# -------------------------------------------------------------------
app = FastAPI(title="Trawa Flex API", version="1.4")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB
DB_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
db = BatteryDatabase(str(DB_FILE_PATH))

# Prevent concurrent pipeline runs (your scripts write shared filenames)
PIPELINE_LOCK = asyncio.Lock()

# -------------------------------------------------------------------
# 🔎 Debug helpers
# -------------------------------------------------------------------
def _file_debug(p: Path) -> str:
    if not p.exists():
        return f"{p} DOES NOT EXIST"
    st = p.stat()
    return f"{p} size={st.st_size} mtime={datetime.fromtimestamp(st.st_mtime).isoformat()}"


def _run_step(name: str, cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"\n🧩 STEP: {name}")
    print("CMD:", " ".join(cmd))
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(BACKEND_ROOT),  # critical: consistent working directory for relative paths in scripts
        env=os.environ.copy(),
    )
    print(f"RC={res.returncode}")
    if res.stdout:
        print(f"--- {name} STDOUT ---\n{res.stdout}\n--- END STDOUT ---")
    if res.stderr:
        print(f"--- {name} STDERR ---\n{res.stderr}\n--- END STDERR ---")
    return res


# -------------------------------------------------------------------
# 🌐 Routes
# -------------------------------------------------------------------
@app.get("/")
def index():
    return {"message": "✅ Trawa Flex API is running!"}


@app.get("/api/health")
def health_check():
    return {"status": "ok", "pipeline_ready": PREDICTION_DIR.exists()}


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
    if not ENET_USERNAME or not ENET_PASSWORD:
        raise HTTPException(status_code=500, detail="Enet credentials not set in .env")

    url = build_enet_rlm_url(
        postCode, location, street, houseNumber, yearlyConsumption, maxPeak, startDate
    )
    print(f"📡 Requesting Enet: {url}")

    try:
        res = requests.get(url, auth=(ENET_USERNAME, ENET_PASSWORD), timeout=15)
        if res.status_code == 401:
            raise HTTPException(status_code=401, detail="Enet Authentication failed")
        res.raise_for_status()
        return res.json()

    except requests.exceptions.RequestException as e:
        print(f"❌ Enet Network Error: {e}")
        raise HTTPException(status_code=500, detail=f"Enet request failed: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected Enet Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/simulation-timeseries")
def get_simulation_timeseries():
    """Returns the latest preprocessed timeseries data."""
    if not FRONTEND_DATA_DIR.exists():
        raise HTTPException(status_code=404, detail="Data directory not found")

    files = list(FRONTEND_DATA_DIR.glob("*_preprocessed.csv"))
    if not files:
        raise HTTPException(status_code=404, detail="No preprocessed timeseries found.")
    target_file = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[0]

    try:
        df = pd.read_csv(target_file)
        if "timestamp_utc" in df.columns:
            numeric_cols = df.select_dtypes(include=["float64", "float32"]).columns
            df[numeric_cols] = df[numeric_cols].round(2)
            df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"]).dt.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        return {"filename": target_file.name, "data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read CSV: {str(e)}")


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
    client_name, run_name = "Web_Submission", f"Run_{uuid.uuid4().hex[:8]}"
    python_exec = sys.executable

    # 1) Save File (shared filename that downstream scripts expect)
    input_csv_path = FRONTEND_DATA_DIR / "input_load.csv"
    try:
        with open(input_csv_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Failed to save file: {str(e)}"})

    # 2) Save Parameters
    params = {
        "list_battery_usable_max_state": list_battery_usable_max_state,
        "list_battery_num_annual_cycles": list_battery_num_annual_cycles,
        "list_battery_proportion_hourly_max_load": list_battery_proportion_hourly_max_load,
        "pv_peak_power": pv_peak_power,
        "pv_consumed_percentage": pv_consumed_percentage,
        "static_grid_fees": static_grid_fees,
        "grid_fee_max_load_peak": grid_fee_max_load_peak,
        "pv_annual_total": pv_peak_power * 1000,
        "working_price_eur_per_kwh": static_grid_fees,
        "power_price_eur_per_kw": grid_fee_max_load_peak,
        "list_battery_max_state": list_battery_usable_max_state / 0.92,
        "list_battery_efficiency": 0.92,
        "list_battery_usability": 0.92,
    }

    with open(INPUT_JSON_PATH, "w") as f:
        json.dump(params, f, indent=2)

    # 3) Run Pipeline Scripts (serialized + no stale outputs)
    async with PIPELINE_LOCK:
        print("\n" + "=" * 80)
        print(f"🚀 Starting Prediction Pipeline for {run_name} @ {datetime.now().isoformat()}")
        print("INPUT CSV:", _file_debug(input_csv_path))
        print("INPUT JSON:", _file_debug(INPUT_JSON_PATH))

        # Delete stale artifacts so you never return old numbers
        if OUTPUT_JSON_PATH.exists():
            OUTPUT_JSON_PATH.unlink()
            print(f"🧹 Deleted stale output: {OUTPUT_JSON_PATH}")

        if PREPROCESSED_CSV_PATH.exists():
            PREPROCESSED_CSV_PATH.unlink()
            print(f"🧹 Deleted stale preprocessed: {PREPROCESSED_CSV_PATH}")

        if WORKING_FEATURES_PATH.exists():
            WORKING_FEATURES_PATH.unlink()
            print(f"🧹 Deleted stale features: {WORKING_FEATURES_PATH}")

        # Step 1: Preprocess
        proc_res = _run_step(
            "preprocess",
            [
                python_exec,
                str(PREDICTION_DIR / "preprocess_load_and_pv.py"),
                "--load",
                str(input_csv_path),
                "--inputs",
                str(INPUT_JSON_PATH),
            ],
        )
        if proc_res.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Preprocess failed: {proc_res.stderr}")

        print("PREPROCESSED CSV:", _file_debug(PREPROCESSED_CSV_PATH))
        if not PREPROCESSED_CSV_PATH.exists():
            raise HTTPException(
                status_code=500,
                detail="Preprocess did not produce input_load_preprocessed.csv (file missing).",
            )

        # Step 2: Features
        feat_res = _run_step(
            "calculate_features",
            [
                python_exec,
                str(PREDICTION_DIR / "calculate_features.py"),
                "--input",
                str(PREPROCESSED_CSV_PATH),
                "--inputs",
                str(INPUT_JSON_PATH),
            ],
        )
        if feat_res.returncode != 0:
            raise HTTPException(
                status_code=500, detail=f"Feature calculation failed: {feat_res.stderr}"
            )

        print("FEATURES JSON:", _file_debug(WORKING_FEATURES_PATH))
        if not WORKING_FEATURES_PATH.exists():
            raise HTTPException(
                status_code=500,
                detail="calculate_features did not produce working_data/features.json (file missing).",
            )

        # Step 3: Predict (✅ pass explicit features + output paths)
        pred_res = _run_step(
            "predict",
            [
                python_exec,
                str(PREDICTION_DIR / "predict_buckets.py"),
                "--features",
                str(WORKING_FEATURES_PATH),
                "--output",
                str(OUTPUT_JSON_PATH),
            ],
        )
        if pred_res.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Prediction failed: {pred_res.stderr}")

        print("OUTPUT JSON:", _file_debug(OUTPUT_JSON_PATH))
        if not OUTPUT_JSON_PATH.exists():
            raise HTTPException(
                status_code=500,
                detail="Predict did not produce outputs_for_frontend.json (file missing).",
            )

    # 4) Read Results (no silent fallback)
    try:
        print(f"📖 Reading results from: {OUTPUT_JSON_PATH}")
        with open(OUTPUT_JSON_PATH, "r") as f:
            data = json.load(f)
        results = {k: (v if v is not None else 0) for k, v in data.items()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading prediction results: {str(e)}")

    # 5) DB Logging
    try:
        db.add_run(client_name, run_name, "Web Submission", params, datetime.now())
        db.add_battery_config(
            client_name,
            run_name,
            f"{int(list_battery_usable_max_state)}kWh",
            False,
            list_battery_usable_max_state,
            list_battery_usable_max_state * list_battery_proportion_hourly_max_load,
        )
    except Exception as e:
        print(f"⚠️ DB logging failed (ignored): {e}")

    return {"message": "Success", "run_id": run_name, "results": results}
