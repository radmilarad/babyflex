#!/usr/bin/env python3
"""
Visualisierung: Warum performt das Modell schlecht? (peak_shaving_benefit)
============================================================================

Lädt die gleichen Daten und den gleichen Train/Test-Split wie 3_train_models,
trainiert ein Modell (wie Step 3) und erzeugt Diagnose-Plots:
  - usage_hours Verteilung + Grenze 6000h
  - Stichproben pro Client (Train vs Test)
  - Target-Verteilung (gesamt vs Train vs Test)
  - Top-Feature vs Target, gefärbt nach Train/Test
  - Actual vs Predicted (Test): Einzelne Ausreißer oder alle daneben?
  - Residuen pro Test-Fall (wer treibt den Fehler?)

Aus Projektroot (DB):  python 2_ml/visualize_training_diagnostics.py
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Gleiche Datenquelle und Konstante wie Training
from importlib import import_module
_train = import_module("2_ml.training.train_models")
_config = import_module("2_ml.config_models")
prepare_data = _train.prepare_data
PEAK_SHAVING_USAGE_HOURS_MAX = getattr(_config, "PEAK_SHAVING_USAGE_HOURS_MAX", 6000.0)
PEAK_SHAVING_USAGE_HOURS_FEATURE = getattr(_config, "PEAK_SHAVING_USAGE_HOURS_FEATURE", "ts__usage_hours")
TARGET = "target_peak_shaving_benefit"
SPLIT_SEED = 42
TEST_SIZE = 0.2
OUT_DIR = Path(__file__).resolve().parent / "artifacts" / "diagnostics"
ARTIFACTS_FEATURES = Path(__file__).resolve().parent / "artifacts" / "features"


def _get_feature_cols_for_peak_shaving():
    """Wie Training: selected_feature_list.txt für peak_shaving_benefit, falls vorhanden."""
    path = ARTIFACTS_FEATURES / "peak_shaving_benefit" / "selected_feature_list.txt"
    if path.exists():
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return lines
    return None


def main():
    print("Lade Feature-Matrix (wie beim Training)...")
    X, df, _ = prepare_data()
    n_total = len(df)
    print(f"  Zeilen gesamt: {n_total}")

    # Filter wie für peak_shaving_benefit: usage_hours <= 6000
    if PEAK_SHAVING_USAGE_HOURS_FEATURE in X.columns:
        mask = (X[PEAK_SHAVING_USAGE_HOURS_FEATURE].isna()) | (
            X[PEAK_SHAVING_USAGE_HOURS_FEATURE] <= PEAK_SHAVING_USAGE_HOURS_MAX
        )
        X_f = X.loc[mask]
        df_f = df.loc[mask]
    else:
        X_f, df_f = X, df
        mask = pd.Series(True, index=X.index)
    n_after = len(df_f)
    print(f"  Nach Filter usage_hours <= {PEAK_SHAVING_USAGE_HOURS_MAX}: {n_after}")

    y = df_f[TARGET]
    valid = y.notna()
    X_clean = X_f[valid]
    y_clean = y[valid]
    df_clean = df_f.loc[valid.index]
    n_valid = len(y_clean)
    print(f"  Mit nicht-leerem Target: {n_valid}")

    groups = df_clean["client_name"] if "client_name" in df_clean.columns else None
    n_groups = groups.nunique() if groups is not None else 0
    print(f"  Clients (Gruppen): {n_groups}")

    # Gleicher Split wie Training (GroupShuffleSplit, seed=42)
    if groups is not None and n_groups >= 2:
        gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=SPLIT_SEED)
        train_idx, test_idx = next(gss.split(X_clean, y_clean, groups))
        train_mask = pd.Series(False, index=X_clean.index)
        train_mask.iloc[train_idx] = True
        test_mask = ~train_mask
    else:
        rng = np.random.RandomState(SPLIT_SEED)
        idx = np.arange(len(X_clean))
        rng.shuffle(idx)
        n_test = max(1, int(len(X_clean) * TEST_SIZE))
        test_idx = idx[:n_test]
        train_idx = idx[n_test:]
        train_mask = pd.Series(False, index=X_clean.index)
        train_mask.iloc[train_idx] = True
        test_mask = ~train_mask

    y_train = y_clean[train_mask]
    y_test = y_clean[test_mask]
    n_train = train_mask.sum()
    n_test = test_mask.sum()
    print(f"  Train: {n_train}, Test: {n_test}")

    # Feature-Subset wie beim Training (selected_feature_list.txt)
    feat_cols = _get_feature_cols_for_peak_shaving()
    if feat_cols:
        available = [c for c in feat_cols if c in X_clean.columns]
        if available:
            X_clean = X_clean[available]
            print(f"  Features (aus selected_feature_list): {len(available)}")

    # Modell trainieren (gleicher Typ wie Step 3) und auf Test vorhersagen
    print("\nTrainiere Modell (GradientBoosting, wie Step 3) für Vorhersage-Diagnose...")
    X_train = X_clean.loc[train_mask]
    X_test = X_clean.loc[test_mask]
    model = GradientBoostingRegressor(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X_train, y_train)
    y_pred_test = model.predict(X_test)
    y_actual_test = y_test.values
    residuals = y_actual_test - y_pred_test
    abs_residuals = np.abs(residuals)
    test_r2 = r2_score(y_actual_test, y_pred_test)
    test_mae = mean_absolute_error(y_actual_test, y_pred_test)
    print(f"  Test R² = {test_r2:.3f}, Test MAE = {test_mae:.2f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not HAS_MATPLOTLIB:
        print("Hinweis: matplotlib nicht installiert → nur Text-Interpretation. Für Plots: pip install matplotlib")

    # --- Plot 1: usage_hours Verteilung + Grenze ---
    if HAS_MATPLOTLIB:
        fig1, axes = plt.subplots(1, 2, figsize=(12, 4))
    if HAS_MATPLOTLIB:
        if PEAK_SHAVING_USAGE_HOURS_FEATURE in X_f.columns:
            u = X_f[PEAK_SHAVING_USAGE_HOURS_FEATURE].dropna()
            axes[0].hist(u, bins=min(50, max(10, len(u) // 5)), edgecolor="gray", alpha=0.8)
            axes[0].axvline(PEAK_SHAVING_USAGE_HOURS_MAX, color="red", linestyle="--", label=f"Grenze {PEAK_SHAVING_USAGE_HOURS_MAX}h")
            axes[0].set_xlabel("usage_hours")
            axes[0].set_ylabel("Anzahl")
            axes[0].set_title("Verteilung usage_hours (vor Filter)")
            axes[0].legend()
        else:
            axes[0].text(0.5, 0.5, "ts__usage_hours nicht in Matrix", ha="center", va="center")
        # Stichproben pro Client
        if groups is not None:
            g = groups.loc[X_clean.index]
            train_clients = g[train_mask].value_counts()
            test_clients = g[test_mask].value_counts()
            idx = train_clients.index.union(test_clients.index)
            all_clients = pd.DataFrame(index=idx)
            all_clients["Train"] = train_clients.reindex(idx).fillna(0)
            all_clients["Test"] = test_clients.reindex(idx).fillna(0)
            all_clients = all_clients.sort_values("Train", ascending=True)
            all_clients.plot(kind="barh", ax=axes[1], color=["#2ecc71", "#e74c3c"], alpha=0.9)
            axes[1].set_xlabel("Anzahl Zeilen")
            axes[1].set_title("Zeilen pro Client (Train vs Test)")
            axes[1].legend(loc="lower right")
        else:
            axes[1].text(0.5, 0.5, "Keine client_name Spalte", ha="center", va="center")
        plt.tight_layout()
        fig1.savefig(OUT_DIR / "01_usage_hours_and_clients.png", dpi=120)
        plt.close(fig1)
        print(f"  → {OUT_DIR / '01_usage_hours_and_clients.png'}")

    # --- Plot 2: Target-Verteilung (gesamt, Train, Test) ---
    if HAS_MATPLOTLIB:
        fig2, axes = plt.subplots(1, 3, figsize=(12, 4))
        for ax, (label, data) in [
            (axes[0], ("Alle (n={})".format(len(y_clean)), y_clean)),
            (axes[1], ("Train (n={})".format(n_train), y_train)),
            (axes[2], ("Test (n={})".format(n_test), y_test)),
        ]:
            ax.hist(data.dropna(), bins=min(30, max(5, len(data) // 3)), edgecolor="gray", alpha=0.8)
            ax.set_xlabel(TARGET)
            ax.set_ylabel("Anzahl")
            ax.set_title(label)
            if len(data) > 0:
                ax.axvline(data.mean(), color="red", linestyle="--", alpha=0.8, label=f"Mean={data.mean():.1f}")
                ax.legend(fontsize=8)
        plt.tight_layout()
        fig2.savefig(OUT_DIR / "02_target_distribution.png", dpi=120)
        plt.close(fig2)
        print(f"  → {OUT_DIR / '02_target_distribution.png'}")

    # --- Plot 3: Top-Feature vs Target, Train vs Test ---
    if HAS_MATPLOTLIB:
        top_feat = "ts__consumption_load_kwh_mean"
        if top_feat in X_clean.columns:
            fig3, ax = plt.subplots(figsize=(8, 5))
            x_all = X_clean[top_feat]
            ax.scatter(
                x_all[train_mask],
                y_clean[train_mask],
                alpha=0.6,
                s=25,
                c="#2ecc71",
                label=f"Train (n={n_train})",
            )
            ax.scatter(
                x_all[test_mask],
                y_clean[test_mask],
                alpha=0.6,
                s=25,
                c="#e74c3c",
                label=f"Test (n={n_test})",
            )
            ax.set_xlabel(top_feat)
            ax.set_ylabel(TARGET)
            ax.set_title("Top-Feature vs Target (Train vs Test)\n→ Wenn Test-Punkte anders liegen, erklärt das schlechten Test-R²")
            ax.legend()
            plt.tight_layout()
            fig3.savefig(OUT_DIR / "03_feature_vs_target.png", dpi=120)
            plt.close(fig3)
            print(f"  → {OUT_DIR / '03_feature_vs_target.png'}")

    # --- Plot 4: Actual vs Predicted (Test) – Einzelne Ausreißer oder alle daneben? ---
    if HAS_MATPLOTLIB and n_test > 0:
        fig4, ax = plt.subplots(figsize=(7, 7))
        lim_min = min(y_actual_test.min(), y_pred_test.min())
        lim_max = max(y_actual_test.max(), y_pred_test.max())
        margin = (lim_max - lim_min) * 0.05 or 1
        ax.plot([lim_min - margin, lim_max + margin], [lim_min - margin, lim_max + margin], "k--", alpha=0.7, label="Perfekt (y=x)")
        if groups is not None:
            g_test = groups.loc[X_clean.index][test_mask]
            uniq = g_test.unique()
            colors = plt.cm.tab10(np.linspace(0, 1, max(len(uniq), 1)))
            for i, cl in enumerate(uniq):
                m = g_test == cl
                ax.scatter(
                    y_actual_test[m],
                    y_pred_test[m],
                    alpha=0.8,
                    s=40,
                    c=[colors[i % len(colors)]],
                    label=str(cl),
                )
        else:
            ax.scatter(y_actual_test, y_pred_test, alpha=0.7, s=40, c="#3498db", label="Test")
        ax.set_xlabel("Tatsächlicher Wert (Actual)")
        ax.set_ylabel("Vorhergesagter Wert (Predicted)")
        ax.set_title("Actual vs Predicted (nur Test-Set)\nPunkte auf der Linie = gut; viele daneben = systematisch schlecht")
        ax.set_xlim(lim_min - margin, lim_max + margin)
        ax.set_ylim(lim_min - margin, lim_max + margin)
        ax.legend(loc="best", fontsize=8)
        ax.set_aspect("equal")
        plt.tight_layout()
        fig4.savefig(OUT_DIR / "04_actual_vs_predicted.png", dpi=120)
        plt.close(fig4)
        print(f"  → {OUT_DIR / '04_actual_vs_predicted.png'}")

    # --- Plot 5: Residuen pro Test-Fall (wer treibt den Fehler?) ---
    if HAS_MATPLOTLIB and n_test > 0:
        fig5, axes = plt.subplots(1, 2, figsize=(12, 5))
        # Links: Absolut-Residuen sortiert (größte Fehler zuerst)
        order = np.argsort(abs_residuals)[::-1]
        ax = axes[0]
        colors = ["#e74c3c" if abs_residuals[i] > np.median(abs_residuals) * 2 else "#95a5a6" for i in order]
        ax.bar(range(n_test), abs_residuals[order], color=colors)
        ax.set_xlabel("Test-Fall (sortiert nach |Fehler|)")
        ax.set_ylabel("|Actual − Predicted|")
        ax.set_title("Absolute Fehler pro Test-Fall\nRote Balken = überdurchschnittlich große Fehler")
        # Rechts: Residuen-Verteilung (Histogramm)
        axes[1].hist(residuals, bins=min(20, max(5, n_test // 2)), edgecolor="gray", alpha=0.8)
        axes[1].axvline(0, color="red", linestyle="--", alpha=0.8)
        axes[1].set_xlabel("Residuum (Actual − Predicted)")
        axes[1].set_ylabel("Anzahl")
        axes[1].set_title("Verteilung der Residuen\nZentriert um 0 = kein systematischer Bias")
        plt.tight_layout()
        fig5.savefig(OUT_DIR / "05_residuals_per_case.png", dpi=120)
        plt.close(fig5)
        print(f"  → {OUT_DIR / '05_residuals_per_case.png'}")

    # Kurz-Interpretation ausgeben
    print("\n" + "=" * 60)
    print("Kurz-Interpretation (warum Test-R² schlecht sein kann)")
    print("=" * 60)
    if len(y_train) > 0 and len(y_test) > 0:
        mean_train = y_train.mean()
        mean_test = y_test.mean()
        std_train = y_train.std()
        std_test = y_test.std()
        print(f"  Target Mittelwert:  Train = {mean_train:.2f}  (Std {std_train:.2f}),  Test = {mean_test:.2f}  (Std {std_test:.2f})")
        if std_test > 1e-6 and abs(mean_test - mean_train) / std_test > 1:
            print("  → Train- und Test-Mittelwert weichen stark ab: Test-Clients verhalten sich anders.")
    if n_test < 10:
        print("- Sehr wenig Test-Daten → R² instabil / oft negativ.")
    if n_groups < 5:
        print("- Wenige Clients → Group-Split legt ganze Clients in Test; wenn einer anders ist, bricht Test-R² ein.")
    if groups is not None and n_test > 0:
        test_client_names = groups.loc[X_clean.index][test_mask].unique().tolist()
        print(f"- Test-Clients in diesem Split: {test_client_names}")

    # Was treibt die schlechte Performance? Einzelne Ausreißer oder alle daneben?
    print("\n" + "=" * 60)
    print("Was treibt den Fehler? Einzelne Test-Fälle oder alle daneben?")
    print("=" * 60)
    if n_test > 0:
        total_ae = abs_residuals.sum()
        order = np.argsort(abs_residuals)[::-1]
        top_k = min(3, n_test)
        top_ae = abs_residuals[order[:top_k]].sum()
        pct_top = (top_ae / total_ae * 100) if total_ae > 0 else 0
        print(f"  Test R² = {test_r2:.3f},  MAE = {test_mae:.2f}")
        print(f"  Anteil des absoluten Fehlers von den {top_k} schlechtesten Test-Fällen: {pct_top:.0f}%")
        if pct_top > 60:
            print("  → Wenige Ausreißer treiben den Fehler (z. B. ein Client oder wenige Konfigurationen).")
        else:
            print("  → Fehler verteilt auf viele Fälle (nicht nur einzelne Ausreißer).")
        print("\n  Größte Fehler (Actual → Predicted, Residuum):")
        for i in range(min(5, n_test)):
            idx = order[i]
            a, p = y_actual_test[idx], y_pred_test[idx]
            r = residuals[idx]
            client = ""
            if groups is not None:
                client = " [" + str(groups.loc[X_clean.index][test_mask].iloc[idx]) + "]"
            print(f"    {a:.1f} → {p:.1f}  (Residuum {r:+.1f}){client}")
    if HAS_MATPLOTLIB:
        print("\n- Plots in:", OUT_DIR)
        print("  (04: Actual vs Predicted, 05: Residuen pro Test-Fall)")
        print("  (01–03: usage_hours, Target-Verteilung, Feature vs Target)")


if __name__ == "__main__":
    main()
