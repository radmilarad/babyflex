# ML Artifacts

All ML outputs live under this directory:

- **features/** – Feature matrix (Parquet), metadata, processed configs (from extraction pipeline)
- **models/** – Trained models (.joblib), registry.json (from training)
- **shap/** – SHAP analysis plots (from evaluate explain_model)

Defaults in code point here; no separate top-level `features/`, `models/`, or `outputs/` folders.
