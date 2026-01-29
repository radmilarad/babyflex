import pandas as pd
from pathlib import Path

CSV_PATH = Path("database/netzbetreiberregister.csv")

# Load once at startup
def load_bdew_data():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"BDEW CSV not found at {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, sep=";", encoding="utf-8")
    df.columns = [c.strip().lower() for c in df.columns]
    return df

BDEW_DF = load_bdew_data()

def find_bdew_by_postcode(postcode: str):
    """Find grid operator for a given postal code."""
    results = BDEW_DF[BDEW_DF["plz"].astype(str).str.startswith(str(postcode))]
    if results.empty:
        return None
    row = results.iloc[0]
    return {
        "bdew_code": row.get("bdew_code") or row.get("bdew-code") or row.get("bdewcode"),
        "operator": row.get("netzbetreiber"),
        "city": row.get("ort"),
        "postcode": row.get("plz"),
    }
