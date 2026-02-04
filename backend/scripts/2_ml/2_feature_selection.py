#!/usr/bin/env python3
"""
Step 2: Feature-Auswahl (nur Target-Level)
==========================================

Läuft nach 1_extract_features. Arbeitet ausschließlich pro Target; alle Ausgaben in
artifacts/features/<target>/ (Blacklist, Korrelation, selected_feature_list.txt, etc.).

Target-Auswahl (eine der drei Möglichkeiten):
  • Interaktiv: Kein --target und kein --report-all → Prompt "Target? 1=..., 2=..., 3=..., 4=..., 5=alle"
     1 = peak_shaving_benefit
     2 = energy_procurement_optimization
     3 = trading_revenue
     4 = peak_shaving_benefit_peak_usage_hours (4. Modell, Sondermodell)
     5 = alle vier
  • --target SPALTE   Ein Target (z. B. target_peak_shaving_benefit).
  • --report-all      Alle vier Targets.

Unterordner: peak_shaving_benefit, energy_procurement_optimization, trading_revenue,
peak_shaving_benefit_peak_usage_hours. Mit --init-targets nur Ordner + blacklist.txt anlegen.

Reports (alle in den jeweiligen Unterordner):
  --correlations, --variance, --target-correlation, --univariate, --redundancy-summary, --report-all.
  --from-correlation  Reduktion anhand correlation_high_r.csv im Unterordner.
  --cv-select         RFECV (LinearRegression, cv=5, R²): Feature-Subset per Cross-Validation → cv_selected_features.txt, cv_selection_report.csv.

  python 2_ml/2_feature_selection.py --init-targets
  python 2_ml/2_feature_selection.py --report-all --no-plot
  python 2_ml/2_feature_selection.py --target target_peak_shaving_benefit --correlations --no-plot
"""
import sys
from pathlib import Path
from typing import Optional, List

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import argparse

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts" / "features"
FEATURE_MATRIX_PATH = ARTIFACTS_DIR / "feature_matrix.parquet"
FEATURE_LIST_PATH = ARTIFACTS_DIR / "feature_list.txt"
SELECTED_LIST_PATH = ARTIFACTS_DIR / "selected_feature_list.txt"
CORRELATION_MATRIX_PATH = ARTIFACTS_DIR / "correlation_matrix.csv"
CORRELATION_HIGH_R_PATH = ARTIFACTS_DIR / "correlation_high_r.csv"
CORRELATION_HEATMAP_PATH = ARTIFACTS_DIR / "correlation_heatmap.png"
VARIANCE_REPORT_PATH = ARTIFACTS_DIR / "variance_report.csv"
REDUNDANCY_SUMMARY_PATH = ARTIFACTS_DIR / "redundancy_summary.csv"

# Target-Spalten in der Feature-Matrix (für --target-correlation / --report-all)
TARGET_COLS = [
    "target_peak_shaving_benefit",
    "target_energy_procurement_optimization",
    "target_trading_revenue",
]
# 4. Modell (Sondermodell) – gleicher Key wie in config_feature_selection.py
TARGET_PEAK_USAGE_HOURS_KEY = "target_peak_shaving_benefit_peak_usage_hours"
ALL_TARGET_KEYS = TARGET_COLS + [TARGET_PEAK_USAGE_HOURS_KEY]

# Unterordner pro Target unter artifacts/features/ (kurze Namen, ohne target_-Prefix)
def _target_to_subfolder(target_key: str) -> str:
    if target_key == TARGET_PEAK_USAGE_HOURS_KEY:
        return "peak_shaving_benefit_peak_usage_hours"
    if target_key.startswith("target_"):
        return target_key.replace("target_", "", 1)
    return target_key


# Interaktive Auswahl: 1–4 = ein Target, 5 = alle
TARGET_CHOICE_TO_KEY = {
    "1": TARGET_COLS[0],                    # target_peak_shaving_benefit
    "2": TARGET_COLS[1],                    # target_energy_procurement_optimization
    "3": TARGET_COLS[2],                    # target_trading_revenue
    "4": TARGET_PEAK_USAGE_HOURS_KEY,       # target_peak_shaving_benefit_peak_usage_hours
    "5": None,                              # None = alle
}


def _prompt_target_choice() -> List[str]:
    """Fragt nach 1–5 und gibt die Liste der zu verarbeitenden Target-Keys zurück."""
    prompt = (
        "Target? 1=peak_shaving_benefit, 2=energy_procurement_optimization, "
        "3=trading_revenue, 4=peak_shaving_benefit_peak_usage_hours, 5=alle: "
    )
    while True:
        try:
            choice = input(prompt).strip()
        except EOFError:
            print("Keine Eingabe (z. B. --target oder --report-all verwenden).")
            return []
        if choice in TARGET_CHOICE_TO_KEY:
            if TARGET_CHOICE_TO_KEY[choice] is None:
                return list(ALL_TARGET_KEYS)
            return [TARGET_CHOICE_TO_KEY[choice]]
        print("Ungültig. Bitte 1, 2, 3, 4 oder 5 eingeben.")

NON_FEATURE_COLS = {"config_id", "client_name", "run_name", "config_name", "target"}


def get_feature_columns(df) -> list:
    """Nur Spalten, die als ML-Features gelten (numerisch, keine IDs/Targets)."""
    import pandas as pd
    out = []
    for c in df.columns:
        if c in NON_FEATURE_COLS or c.startswith("target_"):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            out.append(c)
    return out


def run_correlations(
    feature_matrix_path: Path,
    threshold: float,
    target_filter: Optional[str],
    no_plot: bool,
    feature_whitelist: Optional[List[str]] = None,
    out_dir: Optional[Path] = None,
) -> tuple[Optional[Path], Optional[Path]]:
    """Berechnet Korrelationsmatrix, high_r-Paare und optional Heatmap.
    feature_whitelist: nur diese Features (die in der Matrix existieren).
    out_dir: wenn gesetzt, werden alle Dateien dort geschrieben (correlation_matrix.csv, correlation_high_r.csv, ggf. Heatmap).
    Returns (path_to_matrix_csv, path_to_high_r_csv) für spätere Nutzung (z. B. --from-correlation).
    """
    import pandas as pd

    base = out_dir if out_dir else ARTIFACTS_DIR
    matrix_path = base / "correlation_matrix.csv"
    high_r_path = base / "correlation_high_r.csv"
    heatmap_path = base / "correlation_heatmap.png"

    df = pd.read_parquet(feature_matrix_path)
    feature_cols = get_feature_columns(df)
    if feature_whitelist:
        available = set(df.columns) & set(feature_whitelist)
        feature_cols = [c for c in feature_whitelist if c in available]
        if not feature_cols:
            print("  Keine Features aus der Whitelist in der Matrix gefunden.")
            return None, None
        print(f"  Nur ausgewählte Features: {len(feature_cols)} (Whitelist/effektiv)")
    if not feature_cols:
        print("  Keine numerischen Feature-Spalten gefunden.")
        return None, None
    if target_filter and target_filter in df.columns:
        df = df[df[target_filter].notna()].copy()
        print(f"  Gefiltert auf Target '{target_filter}': {len(df)} Zeilen")
    X = df[feature_cols].copy()
    constant = X.columns[X.nunique() <= 1].tolist()
    if constant:
        X = X.drop(columns=constant)
        feature_cols = X.columns.tolist()
    n_feat = len(feature_cols)
    print(f"  Features: {n_feat}, Zeilen: {len(X)}")
    corr = X.corr()
    corr.to_csv(matrix_path)
    print(f"  Korrelationsmatrix → {matrix_path}")
    high_r = []
    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            r = corr.iloc[i, j]
            if pd.isna(r) or abs(r) < threshold:
                continue
            high_r.append({
                "feature_a": corr.columns[i],
                "feature_b": corr.columns[j],
                "r": round(float(r), 4),
            })
    high_r_df = pd.DataFrame(high_r)
    if not high_r_df.empty:
        high_r_df = high_r_df.reindex(high_r_df["r"].abs().sort_values(ascending=False).index)
    high_r_df.to_csv(high_r_path, index=False)
    print(f"  Stark korrelierte Paare (|r| >= {threshold}): {len(high_r_df)} → {high_r_path}")
    if not no_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("  (Heatmap übersprungen: matplotlib nicht installiert)")
        else:
            fig, ax = plt.subplots(figsize=(max(12, n_feat * 0.25), max(10, n_feat * 0.22)))
            im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
            ax.set_xticks(range(n_feat))
            ax.set_yticks(range(n_feat))
            ax.set_xticklabels(corr.columns, rotation=90, ha="right", fontsize=6)
            ax.set_yticklabels(corr.columns, fontsize=6)
            plt.colorbar(im, ax=ax, label="Korrelation r")
            plt.title("Feature-Korrelationsmatrix")
            plt.tight_layout()
            plt.savefig(heatmap_path, dpi=120)
            plt.close()
            print(f"  Heatmap → {heatmap_path}")
    return matrix_path, high_r_path


def load_current_features() -> list[str]:
    """Liest die aktuelle Feature-Liste (ohne Kommentarzeilen)."""
    if not FEATURE_LIST_PATH.exists():
        return []
    lines = FEATURE_LIST_PATH.read_text(encoding="utf-8").strip().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _blacklist_path(target_key: str) -> Path:
    """Pfad zur Blacklist-Datei für ein Target (im Unterordner)."""
    sub = _target_to_subfolder(target_key)
    return ARTIFACTS_DIR / sub / "blacklist.txt"


def load_blacklist(target_key: str) -> list[str]:
    """Liest Blacklist für ein Target (eine Feature-Zeile pro Zeile, # = Kommentar). Leere/fehlende Datei = keine Blacklist."""
    path = _blacklist_path(target_key)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def get_effective_features_for_target(target_key: str, all_features: Optional[List[str]] = None) -> list[str]:
    """Alle Features minus Blacklist für dieses Target. all_features = None → aus feature_list.txt."""
    if all_features is None:
        all_features = load_current_features()
    black = set(load_blacklist(target_key))
    return [f for f in all_features if f not in black]


def _out_dir_for_target(target_key: str) -> Path:
    """Unterordner für ein Target; wird bei Bedarf erstellt."""
    sub = _target_to_subfolder(target_key)
    d = ARTIFACTS_DIR / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_feature_set_for_target(target_key: str) -> Optional[List[str]]:
    """Liest FEATURE_SETS_PER_TARGET aus config_feature_selection.py (ohne 2_ml-Paket-Import)."""
    import ast
    config_path = Path(__file__).resolve().parent / "config_feature_selection.py"
    if not config_path.exists():
        return None
    text = config_path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    peak_usage_key = "target_peak_shaving_benefit_peak_usage_hours"

    for node in tree.body:
        dict_val = None
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "FEATURE_SETS_PER_TARGET":
                    dict_val = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name) and node.target.id == "FEATURE_SETS_PER_TARGET":
                dict_val = node.value
        if dict_val is None or not isinstance(dict_val, ast.Dict):
            continue
        out = {}
        for k, v in zip(dict_val.keys, dict_val.values):
            key_str = None
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                key_str = k.value
            elif isinstance(k, ast.Name) and k.id == "TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS":
                key_str = peak_usage_key
            if key_str is None:
                continue
            if isinstance(v, ast.Constant) and v.value is None:
                out[key_str] = None
            elif isinstance(v, ast.List):
                lst = []
                for elt in v.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        lst.append(elt.value)
                out[key_str] = lst
        lst = (out or {}).get(target_key)
        return list(lst) if lst else None
    return None


def run_variance_report(
    feature_matrix_path: Path,
    out_path: Path,
    feature_whitelist: Optional[List[str]] = None,
) -> None:
    """Varianz und nunique pro Feature → variance_report.csv. Optional nur feature_whitelist."""
    import pandas as pd
    df = pd.read_parquet(feature_matrix_path)
    feature_cols = get_feature_columns(df)
    if feature_whitelist:
        feature_cols = [c for c in feature_whitelist if c in feature_cols]
    if not feature_cols:
        return
    X = df[feature_cols]
    rows = []
    for c in feature_cols:
        s = X[c].dropna()
        var = float(s.var()) if len(s) > 1 else 0.0
        nuniq = int(s.nunique())
        constant = nuniq <= 1
        near_constant = nuniq <= 2 or (var == 0)
        rows.append({
            "feature": c,
            "variance": round(var, 8),
            "nunique": nuniq,
            "constant": constant,
            "near_constant": near_constant,
        })
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_path, index=False)
    n_const = out_df["constant"].sum()
    n_near = out_df["near_constant"].sum()
    print(f"  Varianz-Report → {out_path}  (constant: {n_const}, near_constant: {n_near})")


def run_target_correlation_reports(
    feature_matrix_path: Path,
    target_cols: List[str],
    weak_r: float,
    target_filter: Optional[str],
    feature_whitelist: Optional[List[str]] = None,
    single_target_out_path: Optional[Path] = None,
) -> None:
    """Pro Target: Korrelation jedes Features mit dem Target. single_target_out_path: nur dieses Target, in diese Datei (für Unterordner)."""
    import pandas as pd
    df = pd.read_parquet(feature_matrix_path)
    feature_cols = get_feature_columns(df)
    if feature_whitelist:
        feature_cols = [c for c in feature_whitelist if c in feature_cols]
    if not feature_cols:
        return
    if single_target_out_path and target_filter:
        available_targets = [target_filter] if target_filter in df.columns else []
    else:
        available_targets = [t for t in target_cols if t in df.columns]
    if not available_targets:
        print("  Keine Target-Spalten in der Matrix gefunden.")
        return
    for tcol in available_targets:
        if target_filter and target_filter != tcol:
            continue
        sub = df[df[tcol].notna()].copy()
        X = sub[feature_cols]
        y = sub[tcol]
        valid = X.notna().all(axis=1) & y.notna()
        X, y = X.loc[valid], y.loc[valid]
        if len(X) < 3:
            print(f"  {tcol}: zu wenig gültige Zeilen, übersprungen.")
            continue
        path = single_target_out_path or (ARTIFACTS_DIR / f"target_correlation_{tcol.replace('target_', '')}.csv")
        rows = []
        for c in feature_cols:
            r = X[c].corr(y)
            r = float(r) if not pd.isna(r) else 0.0
            rows.append({
                "feature": c,
                "r": round(r, 4),
                "abs_r": round(abs(r), 4),
                "weak": abs(r) < weak_r,
            })
        out_df = pd.DataFrame(rows).sort_values("abs_r", ascending=False)
        out_df.to_csv(path, index=False)
        n_weak = out_df["weak"].sum()
        print(f"  Target-Korrelation {tcol} → {path}  (weak |r|<{weak_r}: {n_weak})")
        if single_target_out_path:
            break


def run_univariate_report(
    feature_matrix_path: Path,
    target_col: str,
    target_filter: Optional[str],
    out_path: Path,
    feature_whitelist: Optional[List[str]] = None,
) -> None:
    """Univariate F-Scores (f_regression) vs. ein Target. Optional nur feature_whitelist."""
    import pandas as pd
    try:
        from sklearn.feature_selection import f_regression
    except ImportError:
        print("  sklearn nicht installiert, Univariate-Report übersprungen.")
        return
    df = pd.read_parquet(feature_matrix_path)
    feature_cols = get_feature_columns(df)
    if feature_whitelist:
        feature_cols = [c for c in feature_whitelist if c in feature_cols]
    if target_col not in df.columns or not feature_cols:
        return
    sub = df[df[target_col].notna()].copy()
    if target_filter and target_filter in df.columns:
        sub = sub[sub[target_filter].notna()]
    X = sub[feature_cols].fillna(sub[feature_cols].median())
    y = sub[target_col]
    valid = y.notna()
    X, y = X.loc[valid], y.loc[valid]
    if len(X) < 5:
        print(f"  Univariate ({target_col}): zu wenig Zeilen.")
        return
    f_vals, p_vals = f_regression(X, y)
    rows = []
    for i, c in enumerate(feature_cols):
        rows.append({
            "feature": c,
            "f_value": round(float(f_vals[i]), 4),
            "p_value": round(float(p_vals[i]), 6),
        })
    out_df = pd.DataFrame(rows).sort_values("f_value", ascending=False)
    out_df.to_csv(out_path, index=False)
    print(f"  Univariate vs. {target_col} → {out_path}")


def run_cv_feature_selection(
    feature_matrix_path: Path,
    target_col: str,
    feature_whitelist: List[str],
    out_dir: Path,
    cv: int = 5,
) -> None:
    """
    RFECV mit LinearRegression (scoring='r2', cv=5): wählt Feature-Subset per Cross-Validation.
    Schreibt cv_selected_features.txt und cv_selection_report.csv (Feature, selected, ranking) in out_dir.
    """
    import pandas as pd
    try:
        from sklearn.linear_model import LinearRegression
        from sklearn.feature_selection import RFECV
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("  CV-Feature-Selection: sklearn nicht installiert, übersprungen.")
        return
    df = pd.read_parquet(feature_matrix_path)
    available = [c for c in feature_whitelist if c in df.columns]
    if not available or target_col not in df.columns:
        print("  CV-Feature-Selection: keine Features oder Target nicht in Matrix.")
        return
    sub = df[df[target_col].notna()][available + [target_col]].dropna(how="any")
    if len(sub) < 2 * cv:
        print(f"  CV-Feature-Selection: zu wenig Zeilen ({len(sub)}), mind. {2 * cv} für cv={cv} nötig.")
        return
    X = sub[available]
    y = sub[target_col]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    estimator = LinearRegression()
    min_features = min(3, len(available))  # mind. 3 Features, damit CV nicht nur 1 wählt
    selector = RFECV(
        estimator,
        step=1,
        cv=cv,
        scoring="r2",
        n_jobs=-1,
        min_features_to_select=min_features,
    )
    selector.fit(X_scaled, y)
    selected_names = [available[i] for i in range(len(available)) if selector.support_[i]]
    ranking = selector.ranking_
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cv_selected_features.txt").write_text("\n".join(selected_names) + "\n", encoding="utf-8")
    report = pd.DataFrame({
        "feature": available,
        "selected": [1 if selector.support_[i] else 0 for i in range(len(available))],
        "ranking": ranking,
    })
    report = report.sort_values("ranking")
    report.to_csv(out_dir / "cv_selection_report.csv", index=False)
    cv_r2 = selector.cv_results_["mean_test_score"].max()
    print(f"  CV-Feature-Selection → {out_dir / 'cv_selected_features.txt'}  (CV R²={cv_r2:.4f}, {len(selected_names)} von {len(available)})")


def run_redundancy_summary(
    out_path: Path,
    high_r_path: Optional[Path] = None,
) -> None:
    """Aus correlation_high_r.csv: wie oft jedes Feature in starken Paaren vorkommt (Redundanz-Kandidaten)."""
    import pandas as pd
    hr_path = high_r_path or CORRELATION_HIGH_R_PATH
    if not hr_path.exists():
        print("  redundancy-summary: correlation_high_r.csv fehlt. Zuerst --correlations ausführen.")
        return
    try:
        high_r = pd.read_csv(hr_path)
    except pd.errors.EmptyDataError:
        print("  redundancy-summary: Datei leer oder ohne Spalten, übersprungen.")
        return
    if high_r.empty or "feature_a" not in high_r.columns or "feature_b" not in high_r.columns:
        return
    from collections import Counter
    counts = Counter()
    for _, row in high_r.iterrows():
        counts[row["feature_a"]] += 1
        counts[row["feature_b"]] += 1
    out_df = pd.DataFrame([
        {"feature": f, "count_high_r_pairs": c}
        for f, c in counts.most_common()
    ])
    out_df.to_csv(out_path, index=False)
    print(f"  Redundanz-Summary → {out_path}  ({len(out_df)} Features in starken Paaren)")


def reduce_by_correlation(
    features: list[str],
    threshold: float,
    high_r_path: Optional[Path] = None,
) -> list[str]:
    """
    Liest correlation_high_r.csv; pro Paar mit |r| >= threshold wird feature_b
    aus der Auswahl entfernt. high_r_path: Datei mit Paaren (default: Top-Level).
    """
    path = high_r_path or CORRELATION_HIGH_R_PATH
    if not path.exists():
        return features
    import pandas as pd
    try:
        high_r = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return features
    if high_r.empty or "feature_a" not in high_r.columns or "feature_b" not in high_r.columns:
        return features
    to_drop = set()
    feature_set = set(features)
    for _, row in high_r.iterrows():
        r = row.get("r", 0)
        if abs(r) < threshold:
            continue
        a, b = row["feature_a"], row["feature_b"]
        if a in feature_set and b in feature_set:
            to_drop.add(b)
    return [f for f in features if f not in to_drop]


def main():
    parser = argparse.ArgumentParser(
        description="Step 2: Feature selection – Reports (Varianz, Korrelation, Univariate) oder Reduktion → selected_feature_list.txt"
    )
    parser.add_argument(
        "--correlations",
        action="store_true",
        help="Compute and save correlation matrix, high-r pairs, optional heatmap",
    )
    parser.add_argument(
        "--variance",
        action="store_true",
        help="Variance report: variance_report.csv (constant/near-constant features)",
    )
    parser.add_argument(
        "--target-correlation",
        action="store_true",
        help="Per-target correlation feature–target → target_correlation_<name>.csv",
    )
    parser.add_argument(
        "--univariate",
        action="store_true",
        help="Univariate F-scores vs. one target → univariate_scores_<target>.csv (requires --target)",
    )
    parser.add_argument(
        "--redundancy-summary",
        action="store_true",
        help="From correlation_high_r: how often each feature appears in high-r pairs",
    )
    parser.add_argument(
        "--report-all",
        action="store_true",
        help="Run all report steps: correlations, variance, target-correlation, redundancy-summary (no auto-reduction)",
    )
    parser.add_argument(
        "--from-correlation",
        action="store_true",
        help="Reduce features using correlation_high_r.csv (drop one per high-r pair). Computes correlations if missing.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="Correlation threshold for high-r pairs and for --from-correlation (default: 0.9)",
    )
    parser.add_argument("--no-plot", action="store_true", help="Do not generate correlation heatmap")
    parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Ein Target (ohne Prompt). Keys: target_peak_shaving_benefit, target_energy_procurement_optimization, target_trading_revenue, target_peak_shaving_benefit_peak_usage_hours",
    )
    parser.add_argument(
        "--weak-r",
        type=float,
        default=0.1,
        help="For --target-correlation: flag features with |r| < this as weak (default: 0.1)",
    )
    parser.add_argument(
        "--passthrough",
        action="store_true",
        help="Use all features (no reduction). Default if --from-correlation not set.",
    )
    parser.add_argument(
        "--init-targets",
        action="store_true",
        help="Nur Unterordner für alle Targets anlegen (inkl. blacklist.txt). Keine Reports, keine Feature-Matrix nötig.",
    )
    parser.add_argument(
        "--cv-select",
        action="store_true",
        help="RFECV mit LinearRegression (cv=5, R²): Feature-Subset per Cross-Validation; schreibt cv_selected_features.txt + cv_selection_report.csv.",
    )
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.init_targets:
        for t in ALL_TARGET_KEYS:
            out_dir = _out_dir_for_target(t)
            bp = _blacklist_path(t)
            if not bp.exists():
                bp.write_text(
                    "# Blacklist für dieses Target: eine Feature-Zeile pro Zeile.\n"
                    "# Redundanzen und nicht gewünschte Features (werden bei Reports ausgeschlossen).\n",
                    encoding="utf-8",
                )
            print(f"  {_target_to_subfolder(t)}/")
        print(f"\n✅ Unterordner für alle {len(ALL_TARGET_KEYS)} Targets angelegt (blacklist.txt wo fehlend).")
        return

    if args.report_all:
        args.correlations = True
        args.variance = True
        args.target_correlation = True
        args.univariate = True
        args.redundancy_summary = True
        # Heatmap pro Target wird in Datei gespeichert (out_dir), kein no_plot

    # Nur Target-Level: Auswahl per --target, --report-all oder interaktiv 1–5
    targets_to_process: List[str] = []
    if args.target:
        if args.target not in ALL_TARGET_KEYS:
            print(f"Unbekanntes Target: {args.target}. Erlaubt: {ALL_TARGET_KEYS}")
            sys.exit(1)
        targets_to_process = [args.target]
    elif args.report_all:
        targets_to_process = ALL_TARGET_KEYS
    else:
        targets_to_process = _prompt_target_choice()
        if not targets_to_process:
            sys.exit(1)

    # Ohne Report-Flags: alle Reports für die gewählten Targets (Korrelation, Heatmap, Varianz, …)
    if not (args.correlations or args.variance or args.target_correlation or args.univariate or args.redundancy_summary or args.from_correlation):
        args.correlations = True
        args.variance = True
        args.target_correlation = True
        args.univariate = True
        args.redundancy_summary = True
        # Heatmap wird erzeugt (kein no_plot)

    need_matrix = (
        args.correlations
        or args.from_correlation
        or args.variance
        or args.target_correlation
        or args.univariate
    )
    if need_matrix and not FEATURE_MATRIX_PATH.exists():
        print(f"Feature-Matrix nicht gefunden: {FEATURE_MATRIX_PATH}")
        print("Zuerst: python 2_ml/1_extract_features.py")
        sys.exit(1)

    need_correlations = args.correlations or args.from_correlation

    if targets_to_process:
        if not FEATURE_LIST_PATH.exists():
            print(f"Feature-Liste nicht gefunden: {FEATURE_LIST_PATH}")
            print("Zuerst: python 2_ml/1_extract_features.py")
            sys.exit(1)
        all_features = load_current_features()
        if not all_features:
            print("feature_list.txt ist leer.")
            sys.exit(1)
        for t in targets_to_process:
            out_dir = _out_dir_for_target(t)
            # Blacklist-Datei anlegen, falls nicht vorhanden
            bp = _blacklist_path(t)
            if not bp.exists():
                bp.write_text(
                    "# Blacklist für dieses Target: eine Feature-Zeile pro Zeile.\n"
                    "# Redundanzen und nicht gewünschte Features (werden bei Reports ausgeschlossen).\n",
                    encoding="utf-8",
                )
            effective = get_effective_features_for_target(t, all_features)
            target_filter = t if t in TARGET_COLS else "target_peak_shaving_benefit"
            sub_name = _target_to_subfolder(t)
            if need_correlations:
                print(f"Korrelationsanalyse [{sub_name}] …")
                _, high_r_p = run_correlations(
                    FEATURE_MATRIX_PATH,
                    threshold=args.threshold,
                    target_filter=target_filter,
                    no_plot=args.no_plot,
                    feature_whitelist=effective,
                    out_dir=out_dir,
                )
                print()
            if args.redundancy_summary and (out_dir / "correlation_high_r.csv").exists():
                run_redundancy_summary(out_dir / "redundancy_summary.csv", high_r_path=out_dir / "correlation_high_r.csv")
            if args.from_correlation and (out_dir / "correlation_high_r.csv").exists():
                selected = reduce_by_correlation(effective, args.threshold, high_r_path=out_dir / "correlation_high_r.csv")
                print(f"  Reduktion [{sub_name}]: {len(effective)} → {len(selected)} Features")
            else:
                selected = effective
            (out_dir / "selected_feature_list.txt").write_text("\n".join(selected) + "\n", encoding="utf-8")
            print(f"  selected_feature_list → {out_dir / 'selected_feature_list.txt'}")

            # Varianz, Target-Korrelation, Univariate in denselben Unterordner (nur effektive Features)
            if args.variance:
                run_variance_report(FEATURE_MATRIX_PATH, out_dir / "variance_report.csv", feature_whitelist=effective)
            tcol_for_report = t if t in TARGET_COLS else "target_peak_shaving_benefit"
            if args.target_correlation:
                run_target_correlation_reports(
                    FEATURE_MATRIX_PATH,
                    target_cols=TARGET_COLS,
                    weak_r=args.weak_r,
                    target_filter=tcol_for_report,
                    feature_whitelist=effective,
                    single_target_out_path=out_dir / "target_correlation.csv",
                )
            if args.univariate:
                run_univariate_report(
                    FEATURE_MATRIX_PATH,
                    target_col=tcol_for_report,
                    target_filter=tcol_for_report,
                    out_path=out_dir / "univariate_scores.csv",
                    feature_whitelist=effective,
                )
            if args.cv_select:
                run_cv_feature_selection(
                    FEATURE_MATRIX_PATH,
                    target_col=tcol_for_report,
                    feature_whitelist=effective,
                    out_dir=out_dir,
                    cv=5,
                )

        if len(targets_to_process) == 1:
            print(f"\n✅ Fertig. Output → {_out_dir_for_target(targets_to_process[0])}")
        else:
            print("\n✅ Pro-Target-Reports in artifacts/features/<target>/ erzeugt.")


if __name__ == "__main__":
    main()
