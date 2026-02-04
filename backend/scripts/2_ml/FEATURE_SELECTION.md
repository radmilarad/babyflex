# Feature Selection – Vorgehen

## Wie macht man das normalerweise?

### 1. **Filter-Methoden (korrelations-/varianzbasiert)**
- **Korrelation untereinander:** Sehr stark korrelierte Features (z. B. |r| > 0,9) liefern weitgehend dieselbe Information → eines reicht, das andere kann raus (Reduktion von Redundanz).
- **Korrelation mit dem Target:** Features mit sehr schwacher Beziehung zum Ziel (z. B. |r| ≈ 0) tragen wenig bei → Kandidaten zum Streichen (nur in Kombination mit Domain-Wissen).
- **Varianz:** (Fast) konstante Features bringen keinen Informationsgewinn → können entfernt werden.

### 2. **Domain-Wissen**
- Welche Größen sind **sachlich** relevant für das Ziel? (z. B. Peak-Shaving: Lastspitzen, Grid-Gebühren, Batterie; Energy-Procurement: PV, Verbrauch, Preise.)
- Redundante **Beschreibungen derselben Sache** (z. B. mean, p50, median-ähnlich) → eine davon reicht.

### 3. **Embedded / Modell-basiert**
- **Lasso (L1):** setzt unwichtige Koeffizienten auf 0 → man sieht, welche Features das Modell „weglässt“.
- **Feature Importance / SHAP:** welches Feature trägt wie viel zur Vorhersage bei? Nach dem Training in `4_evaluate_models.py` (--shap) oder aus der Registry.

### 4. **Alle Filtermethoden durchgehen – du entscheidest**

Alle ~60 Features nacheinander mit verschiedenen Methoden prüfen; **am Ende entscheidest du** (Domain-Wissen) pro Feature bzw. pro Modell.

**Einmal alle Reports erzeugen:**

```bash
python 2_ml/2_feature_selection.py --report-all --no-plot
```

Das erzeugt in `2_ml/artifacts/features/`:

| Report | Datei(en) | Was prüfen – deine Entscheidung |
|--------|-----------|----------------------------------|
| **Varianz** | `variance_report.csv` | `constant` / `near_constant` = True → Kandidaten zum Streichen (bringen kaum Information). |
| **Korrelation untereinander** | `correlation_matrix.csv`, `correlation_high_r.csv` | Stark korrelierte Paare (|r| ≥ 0,9): von jedem Paar reicht eines; welches behalten, entscheidest du. |
| **Redundanz-Summary** | `redundancy_summary.csv` | Features, die oft in starken Paaren vorkommen → Redundanz-Kandidaten. |
| **Korrelation mit Target** | `target_correlation_peak_shaving_benefit.csv` (und für die anderen Targets) | Spalte `weak` = True: |r| zum Target < 0,1 → Kandidaten zum Streichen (nur mit Domain-Wissen bestätigen). |
| **Univariate (F-Score)** | `univariate_scores_peak_shaving_benefit.csv` (und für die anderen Targets) | Niedriger F-Wert / hoher p-value → Feature trägt wenig zur linearen Beziehung bei (nur Hinweis). |

**Reihenfolge zum Durchgehen (Empfehlung):**

1. **Varianz** → konstant/near-constant raus (klar).
2. **Korrelation untereinander** + **Redundanz-Summary** → pro starkem Paar eines behalten (welches, entscheidest du nach Inhalt).
3. **Target-Korrelation** + **Univariate** pro Ziel → schwache/irrelevante Kandidaten markieren; mit Domain-Wissen final streichen oder behalten.
4. **Feature-Liste pro Target** in `2_ml/config_feature_selection.py` (FEATURE_SETS_PER_TARGET) eintragen – das ist die Quelle der Wahrheit; Training (Step 3) liest nur von dort. Optional: `selected_feature_list.txt` als Arbeitsliste für Schritt 2 (z. B. `--use-selected` ohne `--target`) oder als Ausgangsbasis für `--from-correlation`.

**Korrelationsmatrix pro Target (aus Config):**  
`python 2_ml/2_feature_selection.py --correlations --use-selected --target target_peak_shaving_benefit --no-plot` erzeugt Matrix und `correlation_high_r.csv` nur für die Features, die in `config_feature_selection.py` für dieses Target stehen.

**Optional – automatische Reduktion aus Korrelation:**  
`python 2_ml/2_feature_selection.py --from-correlation --threshold 0.95` schreibt eine reduzierte Liste nach `selected_feature_list.txt` (pro Paar |r| ≥ 0,95 wird ein Feature weggelassen). **Ergebnis prüfen und die gewünschten Listen pro Target in config_feature_selection.py übernehmen.**

---

## Pro-Target-Unterordner und Blacklist

Das Skript arbeitet **nur noch pro Target**; alle Ausgaben landen in den Unterordnern. Ohne `--target` und ohne `--report-all` erscheint eine Eingabeaufforderung: **1** = peak_shaving_benefit, **2** = energy_procurement_optimization, **3** = trading_revenue, **4** = peak_shaving_benefit_peak_usage_hours, **5** = alle.

Mit `--target SPALTE` oder `--report-all` (bzw. Eingabe 5) erzeugt das Skript **pro Target einen Unterordner** unter `2_ml/artifacts/features/`:

- `peak_shaving_benefit/`
- `energy_procurement_optimization/`
- `trading_revenue/`
- `peak_shaving_benefit_peak_usage_hours/` (4. Modell, Sondermodell)

In jedem Ordner:

- **blacklist.txt** – eine Feature-Zeile pro Zeile (Zeilen mit `#` = Kommentar). Alle hier genannten Features werden für dieses Target aus den Reports und der effektiven Feature-Liste ausgeschlossen (Redundanzen, nicht gewünschte Features).
- **Effektive Features** = alle aus `feature_list.txt` minus Blacklist. Darauf basieren Korrelationsmatrix und `selected_feature_list.txt` in diesem Ordner.
- **correlation_matrix.csv**, **correlation_high_r.csv**, ggf. **correlation_heatmap.png** – nur für die effektiven Features.
- **selected_feature_list.txt** – effektive Features (oder nach `--from-correlation` reduziert). Kann als Vorlage für `config_feature_selection.py` dienen.
- **redundancy_summary.csv** – wenn `--redundancy-summary` bzw. `--report-all` (aus der Korrelation in diesem Ordner).

**Beispiel:** Redundanzen und unerwünschte PV-Metriken in die Blacklist schreiben, dann z. B.:

```bash
python 2_ml/2_feature_selection.py --target target_peak_shaving_benefit --correlations --no-plot
```

Korrelationsmatrix und Listen beziehen sich nur noch auf „alle Features minus Blacklist“. Anschließend z. B. `--from-correlation` für eine reduzierte `selected_feature_list.txt` in diesem Ordner, dann die gewünschte Auswahl in `config_feature_selection.py` übernehmen.

---

## Deine Features grob gruppiert

| Gruppe | Beispiele | Hinweis |
|--------|-----------|--------|
| **Direct / KPI** | `static_grid_fees`, `grid_fee_max_load_peak`, `list_battery_*`, `pv_annual_total`, `pv_consumed_percentage` | Oft inhaltlich wichtig; wenig Redundanz untereinander. |
| **Ratio** | `battery_usable_per_sum_consumption`, `battery_usable_per_sum_pv` | Abgeleitet, aber informativ. |
| **Consumption (ts__)** | `ts__consumption_load_kwh_mean`, `*_std`, `*_p50`, `*_p95`, `*_peak_to_mean`, `*_cv`, … | **Viele stark korreliert** (mean ≈ p50, peak_to_mean ≈ peak_to_median, mehrere Percentile). Wenige pro Ziel reichen. |
| **PV (ts__)** | `ts__pv_load_kwh_mean`, `*_std`, `*_p95`, … | Ähnlich: nicht alle Percentile nötig. |
| **Cross-Column** | `ts__consumption_pv_pearson`, `ts__consumption_da_*`, **`ts__usage_hours`** | Oft besonders aussagekräftig (z. B. usage_hours für Peak-Shaving). |

**Sinnvolle Auswahl pro Ziel (Beispiele):**
- **Peak-Shaving:** usage_hours, static_grid_fees, grid_fee_max_load_peak, Batterie-Kennzahlen, wenige Last-Kennzahlen (z. B. mean, peak_to_mean, evtl. peak_load_share).
- **Energy-Procurement:** PV, consumption_mean, consumption_pv_pearson, Batterie/Ratios.
- **Trading:** Last-/Preis-Korrelationen (consumption_da_*), PV, Verbrauch.

---

## Dateien nach `--report-all` (alle in `2_ml/artifacts/features/`)

- **Varianz:** `variance_report.csv` – Spalten `feature`, `variance`, `nunique`, `constant`, `near_constant`.
- **Korrelation untereinander:** `correlation_matrix.csv` (voll), `correlation_high_r.csv` – Paare mit |r| ≥ threshold.
- **Redundanz:** `redundancy_summary.csv` – wie oft jedes Feature in starken Paaren vorkommt (sortiert nach Häufigkeit).
- **Target-Korrelation:** `target_correlation_peak_shaving_benefit.csv`, `target_correlation_energy_procurement_optimization.csv`, `target_correlation_trading_revenue.csv` – pro Feature `r`, `abs_r`, `weak`.
- **Univariate:** `univariate_scores_peak_shaving_benefit.csv` (und für die anderen Targets) – `f_value`, `p_value` pro Feature.
