"""
Model Comparison & Analysis
===========================

Compare all 3 battery benefit models:
- Performance metrics
- Feature importance
- Category analysis (direct inputs vs. load-profile-derived)

Usage:
    python -m 2_ml.training.compare_models

    # Or from Python:
    from 2_ml.training import compare_models, print_model_overview
    compare_models()
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional

from .model_registry import ModelRegistry


def print_model_overview(registry: ModelRegistry = None):
    """
    Print comprehensive overview of all models.
    
    Args:
        registry: ModelRegistry instance (loads default if None)
    """
    if registry is None:
        registry = ModelRegistry()
    
    if not registry.models:
        print("No models registered. Run training first:")
        print("  python -m 2_ml.training.train_models")
        return
    
    _print_summary(registry)
    _print_feature_comparison(registry)
    _print_category_analysis(registry)
    _print_feature_insights(registry)


def compare_models(registry: ModelRegistry = None) -> pd.DataFrame:
    """
    Compare all models and return comparison DataFrame.
    
    Args:
        registry: ModelRegistry instance
    
    Returns:
        DataFrame with feature importance comparison
    """
    if registry is None:
        registry = ModelRegistry()
    
    print_model_overview(registry)
    return _get_comparison_df(registry)


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================

def _print_summary(registry: ModelRegistry):
    """Print performance summary table."""
    print("\n" + "="*80)
    print("MODEL PERFORMANCE SUMMARY")
    print("="*80)
    
    print("\n┌─────────────────────────────────────┬─────────┬─────────┬────────────────┬───────────┐")
    print("│ Target                              │   R²    │   MAE   │     CV R²      │  Samples  │")
    print("├─────────────────────────────────────┼─────────┼─────────┼────────────────┼───────────┤")
    
    for name, info in registry.models.items():
        cv_str = f"{info.cv_r2_mean:.3f}±{info.cv_r2_std:.2f}"
        print(f"│ {name:35s} │ {info.r2_score:7.3f} │ {info.mae:7.1f} │ {cv_str:>14s} │ {info.n_samples:9d} │")
    
    print("└─────────────────────────────────────┴─────────┴─────────┴────────────────┴───────────┘")
    
    print("\nModel Types:")
    for name, info in registry.models.items():
        print(f"  • {name}: {info.model_type}")
    
    if registry.models:
        best = max(registry.models.items(), key=lambda x: x[1].r2_score)
        print(f"\nBest performing: {best[0]} (R² = {best[1].r2_score:.3f})")


def _get_comparison_df(registry: ModelRegistry) -> pd.DataFrame:
    """Build feature comparison DataFrame."""
    all_features = set()
    for info in registry.models.values():
        all_features.update(info.feature_importance.keys())
    
    comparison = []
    for feature in all_features:
        row = {'feature': feature}
        for name, info in registry.models.items():
            row[name] = info.feature_importance.get(feature, 0)
        comparison.append(row)
    
    df = pd.DataFrame(comparison)
    model_cols = [c for c in df.columns if c != 'feature']
    df['mean_importance'] = df[model_cols].mean(axis=1)
    df['max_importance'] = df[model_cols].max(axis=1)
    df['std_importance'] = df[model_cols].std(axis=1)
    
    def get_dominant(row):
        values = {col: row[col] for col in model_cols}
        max_val = max(values.values())
        if max_val == 0:
            return "none"
        dominant = [k for k, v in values.items() if v >= max_val * 0.95]
        return ", ".join(dominant)
    
    df['dominant_model'] = df.apply(get_dominant, axis=1)
    
    return df.sort_values('mean_importance', ascending=False)


def _print_feature_comparison(registry: ModelRegistry, top_n: int = 15):
    """Print feature importance comparison table."""
    print("\n" + "="*80)
    print("FEATURE IMPORTANCE COMPARISON")
    print("="*80)
    
    df = _get_comparison_df(registry)
    model_cols = list(registry.models.keys())
    
    print(f"\nTop {top_n} Features (sorted by mean importance across all models):\n")
    
    feat_width = 45
    col_width = max(14, max(len(c) for c in model_cols) + 2)
    
    header = f"{'Feature':<{feat_width}}"
    for name in model_cols:
        header += f" │ {name:>{col_width}}"
    header += " │ Dominant"
    print(header)
    print("─" * len(header))
    
    for _, row in df.head(top_n).iterrows():
        line = f"{row['feature']:<{feat_width}}"
        for name in model_cols:
            val = row[name]
            if val > 0.001:
                line += f" │ {val:>{col_width}.4f}"
            else:
                line += f" │ {'—':>{col_width}}"
        line += f" │ {row['dominant_model']}"
        print(line)


def _print_category_analysis(registry: ModelRegistry):
    """Analyze features by category (direct inputs vs. load-profile-derived)."""
    print("\n" + "="*80)
    print("FEATURE CATEGORY ANALYSIS")
    print("="*80)
    print("(Anteil der Feature-Kategorien an der Wichtigkeit pro Modell)\n")
    
    categories = {
        'Direct inputs (list_battery_*, pv_*)': lambda f: f.startswith('list_battery_') or f in ('pv_annual_total', 'pv_consumed_percentage'),
        'Load-profile (ts__*)': lambda f: f.startswith('ts__'),
        'Other': lambda f: not (f.startswith('list_battery_') or f in ('pv_annual_total', 'pv_consumed_percentage') or f.startswith('ts__')),
    }
    
    for name, info in registry.models.items():
        print(f"--- {name} ---")
        
        importance = info.feature_importance
        total = sum(importance.values())
        
        if total == 0:
            print("  No feature importance data")
            continue
        
        for cat_name, cat_filter in categories.items():
            cat_features = {f: v for f, v in importance.items() if cat_filter(f)}
            cat_total = sum(cat_features.values())
            pct = (cat_total / total * 100) if total > 0 else 0
            
            bar = "█" * int(pct / 2.5)
            print(f"  {cat_name:<30} {pct:5.1f}% {bar}")
        print()


def _print_feature_insights(registry: ModelRegistry):
    """Print insights about shared and unique features."""
    print("="*80)
    print("FEATURE INSIGHTS")
    print("="*80)
    
    shared = _get_shared_important_features(registry, threshold=0.01)
    if shared:
        print(f"\nFeatures important for ALL models ({len(shared)}):")
        for f in shared[:8]:
            print(f"  • {f}")
        if len(shared) > 8:
            print(f"  ... and {len(shared) - 8} more")
    
    print()
    for name in registry.models.keys():
        unique = _get_unique_important_features(registry, name, threshold=0.02)
        if unique:
            print(f"Uniquely important for {name}:")
            for f in unique[:5]:
                print(f"  • {f}")
    
    print()


def _get_shared_important_features(
    registry: ModelRegistry, 
    threshold: float = 0.01
) -> List[str]:
    """Get features important (> threshold) for ALL models."""
    if not registry.models:
        return []
    
    shared = None
    for info in registry.models.values():
        important = {f for f, v in info.feature_importance.items() if v > threshold}
        if shared is None:
            shared = important
        else:
            shared &= important
    
    return sorted(shared) if shared else []


def _get_unique_important_features(
    registry: ModelRegistry,
    target_name: str, 
    threshold: float = 0.02
) -> List[str]:
    """Get features uniquely important for one model."""
    clean_name = target_name.replace("target_", "")
    if clean_name not in registry.models:
        return []
    
    this_important = {
        f for f, v in registry.models[clean_name].feature_importance.items() 
        if v > threshold
    }
    
    other_important = set()
    for name, info in registry.models.items():
        if name != clean_name:
            other_important.update(
                f for f, v in info.feature_importance.items() 
                if v > threshold / 2
            )
    
    return sorted(this_important - other_important)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    compare_models()
