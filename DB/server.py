from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from battery_db import BatteryDatabase
from benefit_calculator import BenefitCalculator
import numpy as np
import pandas as pd
import json

# -------------------------------------------------------------------
# 🧹 Helper: Convert DataFrame to JSON-safe format
# -------------------------------------------------------------------
def dataframe_to_json(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a JSON string that is fully compliant (no NaN/inf)."""
    if df is None or df.empty:
        return "[]"
    # Replace infinities and NaNs with None
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.astype(object).where(pd.notnull(df), None)
    # Convert safely to JSON string
    return json.dumps(df.to_dict(orient="records"), allow_nan=False)

# -------------------------------------------------------------------
# 🚀 FastAPI App Setup
# -------------------------------------------------------------------
app = FastAPI(title="Trawa Flex API", version="1.2")

# ✅ CORS fix: allow frontend (localhost and 127.0.0.1)
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
def get_kpis(
    client_name: str,
    run_name: str,
    config_name: str = Query(None)
):
    df = db.get_kpis(client_name, run_name, config_name)
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

@app.get("/api/timeseries")
def get_timeseries(
    client_name: str,
    run_name: str,
    config_name: str
):
    df = db.query_timeseries_csv(client_name, run_name, config_name)
    if df.empty:
        return JSONResponse(content={"message": "No timeseries found"})
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

# -------------------------------------------------------------------
# ⚡ Benefit Calculations
# -------------------------------------------------------------------
@app.get("/api/benefits")
def get_benefits(
    client_name: str = Query(None),
    run_name: str = Query(None)
):
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
def compare_configs(
    client_name: str,
    run_name: str,
    kpi_name: str = Query(None)
):
    df = db.compare_configs(client_name, run_name, kpi_name)
    safe_json = dataframe_to_json(df)
    return Response(content=safe_json, media_type="application/json")

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
