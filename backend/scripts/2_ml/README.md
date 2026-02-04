# 2_ml – Feature-Extraktion und Modell-Training

Dokumentation der Konfigurationen und der beiden Modell-Varianten.

---

## Konfigurationsdateien

In `2_ml/` liegen mehrere Configs mit klarer Trennung:

### 1. `config_feature_extraction.py` – Was wird extrahiert (Step 1) – **nicht anfassen**

Definiert, welche Features in 1_extract_features berechnet werden (DIRECT_INPUT_NAMES, LOAD_PROFILE_COLUMN_SPECS, LOAD_PROFILE_DF_FEATURE_NAMES, RATIO_FEATURES, KPI_TARGETS, …). Wird von der Pipeline verwendet. Du musst diese Datei nicht mehr anpassen.

### 2. `config_feature_selection.py` – Feature-Auswahl für alle 4 Modelle – **hier anpassen**

**FEATURE_SETS_PER_TARGET** – Pro Modell eine Whitelist: die drei Targets plus **target_peak_shaving_benefit_peak_usage_hours** (4. Modell, Sondermodell usage_hours > Threshold). Keys: `target_peak_shaving_benefit`, `target_energy_procurement_optimization`, `target_trading_revenue`, `target_peak_shaving_benefit_peak_usage_hours`. Wert `None` = alle Features; Liste = nur diese. Training (Step 3) liest daraus (bzw. aus `artifacts/features/<target>/selected_feature_list.txt` falls vorhanden).

### 3. `config_models.py` – Modell & Training – **hier anpassen (Modell, CV, Grenzen)**

Enthält: PEAK_SHAVING_USAGE_HOURS_MAX, PEAK_SHAVING_USAGE_HOURS_FEATURE (Grenze für Target 1), **PEAK_USAGE_HOURS_THRESHOLD** und **MODELS_DIR_PEAK_USAGE** (für Sondermodell `--target 4`), TRAINING_TARGETS, DEFAULT_MODEL_TYPE, TrainingConfig, …


---

## Die beiden Modell-Ausgaben

| | Standard-Modelle (1–3) | Sondermodell (4) |
|---|------------------------|-------------------|
| **Ordner** | `2_ml/artifacts/models/` | `2_ml/artifacts/models_peak_usage/` |
| **Training** | `python 2_ml/3_train_models.py` (oder `--target 1` / `2` / `3`) | `python 2_ml/3_train_models.py --target 4` |
| **Targets** | 1=peak_shaving, 2=energy_procurement, 3=trading_revenue | peak_shaving nur für **usage_hours >** Threshold |
| **Datenfilter** | Target 1: nur `usage_hours <=` PEAK_SHAVING_USAGE_HOURS_MAX. 2/3: alle Zeilen. | Nur Zeilen mit **usage_hours >** PEAK_USAGE_HOURS_THRESHOLD |
| **Config** | `config_feature_selection.py` + `config_models.py` | Key target_peak_shaving_benefit_peak_usage_hours, MODELS_DIR_PEAK_USAGE |
| **Verwendung Vorhersage** | Standard: 3_prediction nutzt `2_ml/artifacts/models/` | Optional: gezielt models_peak_usage wenn hohe usage_hours |

**Standard-Modelle**  
- Für die normale Vorhersage aller drei Benefits.  
- Werden von 3_prediction (predict_buckets) genutzt, wenn keine Kopie unter `3_prediction/models/` liegt.

**Peak-Usage-Modelle**  
- Nur ein Modell: peak_shaving_benefit, trainiert auf Configs mit hohen Vollbenutzungsstunden.  
- Sinnvoll, wenn peak_shaving vor allem bei hoher Auslastung gut abgebildet werden soll; für die normale Pipeline optional.

---

## Ablauf (Kurz)

1. **Feature-Matrix erzeugen (mit usage_hours):**  
   `python 2_ml/1_extract_features.py`  
   (config_feature_extraction muss usage_hours in LOAD_PROFILE_DF_FEATURE_NAMES enthalten)

2. **Feature-Auswahl (inkl. Korrelationen):**  
   `python 2_ml/2_feature_selection.py`  
   Erzeugt `artifacts/features/selected_feature_list.txt`. Mit `--correlations`: Korrelationsmatrix, `correlation_high_r.csv` und optional Heatmap. Mit `--from-correlation`: Reduktion anhand stark korrelierter Paare (berechnet Korrelationen bei Bedarf automatisch).

3. **Standard-Modelle (alle 3 Targets):**  
   `python 2_ml/3_train_models.py`  
   → Ausgabe: `2_ml/artifacts/models/`

4. **Sondermodell (peak_shaving, nur usage_hours > Threshold):**  
   `python 2_ml/3_train_models.py --target 4`  
   → Ausgabe: `2_ml/artifacts/models_peak_usage/` (Threshold: config_models.PEAK_USAGE_HOURS_THRESHOLD)

5. **Vorhersage (3_prediction):**  
   Nutzt standardmäßig die Modelle aus `3_prediction/models/` oder `2_ml/artifacts/models/`.  
   Für die Peak-Usage-Variante müsste die Prediction-Logik gezielt auf `2_ml/artifacts/models_peak_usage/` zeigen (z.B. per Flag oder eigener Skript-Variante).

---

## Dateien im Überblick

```
2_ml/
├── config_feature_extraction.py   # Step 1 – nicht anfassen
├── config_feature_selection.py   # Feature-Whitelist für alle 4 Modelle (3 Targets + target_peak_shaving_benefit_peak_usage_hours) – hier anpassen
├── config_models.py               # Modell, TRAINING_TARGETS, MODELS_DIR_PEAK_USAGE (Sondermodell), CV – hier anpassen
├── README.md                      # Diese Doku
├── 1_extract_features.py         # Feature-Extraktion → artifacts/features/
├── 2_feature_selection.py        # Feature-Auswahl → selected_feature_list.txt
├── 3_train_models.py             # Training: --target 1|2|3|4 (4 = Sondermodell) → artifacts/models/ bzw. models_peak_usage/
├── 4_evaluate_models.py          # Modell-Evaluation (In-sample, Test/CV aus Training)
├── 5_compare_models.py           # Modell-Vergleich
├── artifacts/
│   ├── features/                 # Feature-Matrix (Parquet), selected_feature_list.txt, correlation_*.csv (via 2_feature_selection --correlations)
│   ├── models/                   # Standard: 3 Modelle + registry.json
│   └── models_peak_usage/        # Peak-Variante: 1 Modell + registry.json
├── extraction/                   # Pipeline, Timeseries-Aggregationen, Feature-Store
└── training/                     # train_models, model_registry, compare_models, …
```
