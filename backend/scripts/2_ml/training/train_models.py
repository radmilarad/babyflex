"""
Model Training
==============

Train all 3 battery benefit models:
- peak_shaving_benefit
- energy_procurement_optimization
- trading_revenue

Modell-Wahl: Entweder hier per CLI (--model) oder per Aufruf train_all_models(model_type=…).
Optional: default_model aus 2_ml.config_models (DEFAULT_CONFIG) nutzen, wenn model_type nicht gesetzt ist.

Usage:
    python -m 2_ml.training.train_models

    # Or from Python:
    from 2_ml.training import train_all_models
    train_all_models()

    # Model type via CLI or argument:
    python -m 2_ml.training.train_models --model ridge
    train_all_models(model_type="ridge")
"""

import time
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Any, Optional, List

# ML imports
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import (
    train_test_split, 
    cross_val_score,
    GroupShuffleSplit,
    GroupKFold,
    LeaveOneGroupOut
)
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error

# Local imports
from .. import FeatureStore
from ..config_models import (
    PEAK_SHAVING_USAGE_HOURS_MAX,
    PEAK_SHAVING_USAGE_HOURS_FEATURE,
    PEAK_USAGE_HOURS_THRESHOLD,
    MODELS_DIR_PEAK_USAGE,
    TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS,
)
from ..config_feature_selection import FEATURE_SETS_PER_TARGET
from .model_registry import ModelRegistry

# Pro-Target Feature-Liste: zuerst aus artifacts/features/<subfolder>/selected_feature_list.txt
ARTIFACTS_FEATURES_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "features"


def _target_to_feature_subfolder(target: str) -> str:
    """target_peak_shaving_benefit -> peak_shaving_benefit; target_peak_shaving_benefit_peak_usage_hours -> peak_shaving_benefit_peak_usage_hours."""
    if target == TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS:
        return "peak_shaving_benefit_peak_usage_hours"
    return target.replace("target_", "", 1)


def _get_feature_list_for_target(target: str) -> Optional[List[str]]:
    """Liest selected_feature_list.txt aus artifacts/features/<subfolder>/. None wenn nicht vorhanden oder leer."""
    subfolder = _target_to_feature_subfolder(target)
    path = ARTIFACTS_FEATURES_DIR / subfolder / "selected_feature_list.txt"
    if not path.exists():
        return None
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return lines if lines else None

# Try XGBoost
try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False


# =============================================================================
# CONFIGURATION
# =============================================================================

TARGETS = [
    "target_peak_shaving_benefit",
    "target_energy_procurement_optimization",
    "target_trading_revenue"
]

# Columns to exclude from features
EXCLUDE_COLS = {"config_id", "client_name", "run_name", "config_name", "target"}


# =============================================================================
# TRAINING FUNCTIONS
# =============================================================================

def _group_cross_val_score(
    model, 
    X: np.ndarray, 
    y: pd.Series, 
    groups: pd.Series,
    cv_folds: int,
    verbose: bool
) -> np.ndarray:
    """
    Perform cross-validation with group-aware splitting.
    
    If groups are provided and there are enough unique groups, uses GroupKFold
    to ensure all samples from one client are in the same fold.
    Falls back to standard KFold otherwise.
    
    Args:
        model: Sklearn estimator
        X: Feature matrix
        y: Target values
        groups: Group labels (e.g., client names)
        cv_folds: Number of folds
        verbose: Print info about CV strategy
    
    Returns:
        Array of R² scores for each fold
    """
    n_samples = len(y)
    n_groups = groups.nunique() if groups is not None else 0
    
    if groups is not None and n_groups >= 2:
        # Use group-aware cross-validation
        actual_folds = min(cv_folds, n_groups)
        
        if n_groups <= 5:
            # With few groups, use Leave-One-Group-Out
            cv = LeaveOneGroupOut()
            if verbose:
                print(f"CV: Leave-One-Group-Out ({n_groups} folds)")
        else:
            cv = GroupKFold(n_splits=actual_folds)
            if verbose:
                print(f"CV: GroupKFold ({actual_folds} folds)")
        
        return cross_val_score(model, X, y, cv=cv, groups=groups, scoring='r2')
    else:
        # Standard cross-validation
        actual_folds = min(cv_folds, n_samples)
        if verbose and groups is not None:
            print(f"CV: Standard KFold ({actual_folds} folds) - not enough groups")
        return cross_val_score(model, X, y, cv=actual_folds, scoring='r2')


def prepare_data(store_dir: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Load and prepare data for training.
    
    Uses script-relative path for FeatureStore if store_dir not given,
    so training works regardless of cwd (aligned with 1_extract_features).
    
    Args:
        store_dir: Optional path to features dir; default: 2_ml/artifacts/features
                   relative to this file (2_ml/training/train_models.py).
    
    Returns:
        X: Feature matrix (imputed)
        df: Full dataframe (for targets)
        feature_names: List of feature column names
    """
    if store_dir is None:
        _ml_root = Path(__file__).resolve().parent.parent  # 2_ml
        store_dir = str(_ml_root / "artifacts" / "features")
    store = FeatureStore(store_dir=store_dir)
    df = store.load_features()
    
    if df.empty:
        raise ValueError("No features found. Run feature extraction first.")
    
    # Define feature columns
    exclude = EXCLUDE_COLS.copy()
    exclude.update(TARGETS)
    feature_cols = [c for c in df.columns if c not in exclude]
    
    X = df[feature_cols]
    
    # Impute missing values
    imputer = SimpleImputer(strategy='median')
    X_imputed = pd.DataFrame(
        imputer.fit_transform(X),
        columns=X.columns,
        index=X.index
    )
    
    return X_imputed, df, feature_cols


def train_single_model(
    X: pd.DataFrame,
    y: pd.Series,
    target_name: str,
    groups: pd.Series = None,
    model_type: str = "auto",
    test_size: float = 0.2,
    cv_folds: int = 5,
    verbose: bool = True,
    test_clients: Optional[List[str]] = None,
    split_seed: int = 42,
) -> Tuple[Any, Dict[str, float], Dict[str, float]]:
    """
    Train a single model for one target.
    
    Args:
        X: Feature matrix
        y: Target values
        target_name: Name of target variable
        groups: Optional Series with group labels (e.g., client_name) for 
                group-aware splitting. Ensures all samples from one client
                are either in train OR test, never both.
        model_type: "xgboost", "gradient_boosting", "ridge", or "auto"
        test_size: Fraction for test set
        cv_folds: Number of cross-validation folds
        verbose: Print progress
        test_clients: If set, these client names go to test set (rest = train). Overrides random group split.
        split_seed: Random seed for group/random split (used when test_clients not set).
    
    Returns:
        model: Trained model
        metrics: Dict with r2, mae, rmse, cv scores
        importance: Dict mapping feature -> importance
    """
    clean_name = target_name.replace("target_", "")
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Training: {clean_name}")
        print(f"{'='*60}")
    
    # Remove NaN targets
    mask = ~y.isna()
    X_clean = X[mask]
    y_clean = y[mask]
    groups_clean = groups[mask] if groups is not None else None
    
    n_samples = len(y_clean)
    n_features = X_clean.shape[1]
    n_groups = groups_clean.nunique() if groups_clean is not None else 0
    
    if verbose:
        print(f"Samples: {n_samples}, Features: {n_features}")
        if groups_clean is not None:
            print(f"Groups (clients): {n_groups}")
        if n_samples < 500:
            print("(Wenige Sekunden Fit-Zeit sind normal bei dieser Stichprobengröße.)")
    
    if n_samples < 10:
        raise ValueError(f"Not enough samples for {clean_name}: {n_samples}")
    
    # Determine model type - default to Gradient Boosted Trees
    if model_type == "auto":
        if HAS_XGB and n_samples >= 50:
            model_type = "xgboost"
        else:
            # Always prefer gradient boosting for interpretability with SHAP
            model_type = "gradient_boosting"
    
    # Train/test split - GROUP-AWARE if groups provided (or explicit test_clients)
    use_group_split = groups_clean is not None and n_groups >= 2
    
    if use_group_split and test_clients is not None and len(test_clients) > 0:
        # Explicit test clients: put these in test, rest in train
        test_client_set = set(c.strip() for c in test_clients if c and isinstance(c, str))
        test_mask = groups_clean.isin(test_client_set)
        test_idx = np.where(test_mask)[0]
        train_idx = np.where(~test_mask)[0]
        if len(test_idx) == 0:
            raise ValueError(f"No samples found for test_clients {test_clients}. Available: {sorted(groups_clean.unique())}")
        if len(train_idx) == 0:
            raise ValueError("All samples would be in test set; need at least one client in train.")
        X_train = X_clean.iloc[train_idx]
        X_test = X_clean.iloc[test_idx]
        y_train = y_clean.iloc[train_idx]
        y_test = y_clean.iloc[test_idx]
        if verbose:
            train_clients = sorted(groups_clean.iloc[train_idx].unique())
            test_clients_actual = sorted(groups_clean.iloc[test_idx].unique())
            print(f"Train clients ({len(train_clients)}): {train_clients}")
            print(f"Test clients ({len(test_clients_actual)}): {test_clients_actual} (explicit)")
    elif use_group_split:
        # Group-aware random split: ensures complete clients in train/test (uses split_seed)
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=split_seed)
        train_idx, test_idx = next(gss.split(X_clean, y_clean, groups_clean))
        X_train = X_clean.iloc[train_idx]
        X_test = X_clean.iloc[test_idx]
        y_train = y_clean.iloc[train_idx]
        y_test = y_clean.iloc[test_idx]
        if verbose:
            train_clients = sorted(groups_clean.iloc[train_idx].unique())
            test_clients_actual = sorted(groups_clean.iloc[test_idx].unique())
            print(f"Train clients ({len(train_clients)}): {train_clients}")
            print(f"Test clients ({len(test_clients_actual)}): {test_clients_actual}")
    else:
        # Standard random split
        X_train, X_test, y_train, y_test = train_test_split(
            X_clean, y_clean, test_size=test_size, random_state=split_seed
        )
        if verbose and groups_clean is not None:
            print("Not enough groups for group-aware split, using random split")

    if verbose:
        print(f"Train/Test split: {len(y_train)} / {len(y_test)} samples (Fit auf Train, Evaluation auf Test)")
    
    # Select and train model
    if model_type == "xgboost" and HAS_XGB:
        if verbose:
            print("Model: XGBoost")
        model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42,
            n_jobs=-1
        )
    elif model_type == "gradient_boosting":
        if verbose:
            print("Model: GradientBoosting")
        model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
    else:
        if verbose:
            print("Model: Ridge (linear)")
        # For Ridge, we need to scale features. Keep as DataFrame with column names
        # so predict() later (e.g. in evaluate) doesn't warn "fitted without feature names".
        scaler = StandardScaler()
        X_train_scaled = pd.DataFrame(
            scaler.fit_transform(X_train),
            columns=X_train.columns,
            index=X_train.index,
        )
        X_test_scaled = pd.DataFrame(
            scaler.transform(X_test),
            columns=X_test.columns,
            index=X_test.index,
        )
        X_clean_scaled = pd.DataFrame(
            scaler.transform(X_clean),
            columns=X_clean.columns,
            index=X_clean.index,
        )
        
        model = Ridge(alpha=1.0)
        t0 = time.perf_counter()
        model.fit(X_train_scaled, y_train)
        if verbose:
            print(f"Fit: {time.perf_counter() - t0:.1f}s")
        # Evaluate
        y_pred = model.predict(X_test_scaled)
        
        metrics = {
            'r2': r2_score(y_test, y_pred),
            'mae': mean_absolute_error(y_test, y_pred),
            'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
        }
        
        # Cross-validation - GROUP-AWARE if groups provided
        cv_scores = _group_cross_val_score(
            model, X_clean_scaled, y_clean, groups_clean, cv_folds, verbose
        )
        metrics['cv_r2_mean'] = cv_scores.mean()
        metrics['cv_r2_std'] = cv_scores.std()
        
        # Feature importance (absolute coefficients)
        importance = dict(zip(X.columns, np.abs(model.coef_)))
        
        if verbose:
            print(f"Test R²: {metrics['r2']:.3f}")
            print(f"Test MAE: {metrics['mae']:.2f}")
            print(f"CV R²: {metrics['cv_r2_mean']:.3f} (±{metrics['cv_r2_std']:.3f})")
        
        return model, metrics, importance
    
    # Train tree-based model
    t0 = time.perf_counter()
    model.fit(X_train, y_train)
    if verbose:
        print(f"Fit: {time.perf_counter() - t0:.1f}s")
    # Evaluate
    y_pred = model.predict(X_test)
    
    metrics = {
        'r2': r2_score(y_test, y_pred),
        'mae': mean_absolute_error(y_test, y_pred),
        'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
    }
    
    # Cross-validation - GROUP-AWARE if groups provided
    cv_scores = _group_cross_val_score(
        model, X_clean, y_clean, groups_clean, cv_folds, verbose
    )
    metrics['cv_r2_mean'] = cv_scores.mean()
    metrics['cv_r2_std'] = cv_scores.std()
    
    # Feature importance
    importance = dict(zip(X.columns, model.feature_importances_))
    
    if verbose:
        print(f"Test R²: {metrics['r2']:.3f}")
        print(f"Test MAE: {metrics['mae']:.2f}")
        print(f"CV R²: {metrics['cv_r2_mean']:.3f} (±{metrics['cv_r2_std']:.3f})")
    
    return model, metrics, importance


def train_all_models(
    model_type: str = "auto",
    group_aware: bool = True,
    verbose: bool = True,
    test_clients: Optional[List[str]] = None,
    split_seed: int = 42,
    targets_filter: Optional[List[str]] = None,
) -> Tuple[ModelRegistry, Optional[ModelRegistry]]:
    """
    Train target models and register them.
    
    Args:
        model_type: "xgboost", "gradient_boosting", "ridge", or "auto"
        group_aware: If True, ensures clients are not split between train/test.
        verbose: Print progress
        targets_filter: If set, only train these targets (e.g. ["target_peak_shaving_benefit"]). Else all TARGETS.
    
    Returns:
        ModelRegistry with trained models
    """
    all_target_keys = TARGETS + [TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS]
    targets_to_train = [t for t in (targets_filter or TARGETS) if t in all_target_keys]
    if not targets_to_train:
        targets_to_train = TARGETS

    print("\n" + "="*60)
    print("TRAINING BATTERY BENEFIT MODELS")
    print("="*60)
    if len(targets_to_train) < len(TARGETS) and verbose:
        print(f"Targets: {', '.join(targets_to_train)}")
    
    # Load data (path script-relative, so cwd-independent like 1_extract_features)
    X, df, feature_names = prepare_data()
    n_total = len(df)
    print(f"Loaded {n_total} samples with {len(feature_names)} features")
    
    # Get client groups for group-aware splitting (per-target: only rows with non-NaN target are used)
    groups = None
    if group_aware and 'client_name' in df.columns:
        groups = df['client_name']
        n_groups_full = groups.nunique()
        print(f"Group-aware splitting: {n_groups_full} unique clients in full data (per-target subset may be smaller)")
        if n_groups_full < 2:
            print("Only 1 client found - falling back to random splits")
            groups = None
    elif group_aware:
        print("No 'client_name' column found - using random splits")
    
    # Initialize registry (4. Modell → separates Registry in MODELS_DIR_PEAK_USAGE)
    registry = ModelRegistry()
    peak_usage_registry: Optional[ModelRegistry] = None

    # Train each model
    for target in targets_to_train:
        is_peak_usage_model = target == TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS
        if is_peak_usage_model:
            y = df["target_peak_shaving_benefit"]
            if PEAK_SHAVING_USAGE_HOURS_FEATURE not in X.columns and PEAK_SHAVING_USAGE_HOURS_FEATURE not in df.columns:
                print(f"\nSkipping {target}: Feature '{PEAK_SHAVING_USAGE_HOURS_FEATURE}' nicht in Matrix.")
                continue
            usage = X[PEAK_SHAVING_USAGE_HOURS_FEATURE] if PEAK_SHAVING_USAGE_HOURS_FEATURE in X.columns else df[PEAK_SHAVING_USAGE_HOURS_FEATURE]
            mask = (usage.notna()) & (usage > PEAK_USAGE_HOURS_THRESHOLD)
            X_use = X.loc[mask]
            y_use = y.loc[mask]
            groups_use = groups[mask] if groups is not None else None
            if verbose:
                print(f"\n  {target}: nur usage_hours > {PEAK_USAGE_HOURS_THRESHOLD} (n={mask.sum()})")
        else:
            y = df[target]
            X_use, y_use, groups_use = X, y, groups
            # peak_shaving_benefit: nur Zeilen mit usage_hours <= PEAK_SHAVING_USAGE_HOURS_MAX
            if target == "target_peak_shaving_benefit" and PEAK_SHAVING_USAGE_HOURS_FEATURE in X.columns:
                mask = (X[PEAK_SHAVING_USAGE_HOURS_FEATURE].isna()) | (X[PEAK_SHAVING_USAGE_HOURS_FEATURE] <= PEAK_SHAVING_USAGE_HOURS_MAX)
                X_use = X.loc[mask]
                y_use = y.loc[mask]
                groups_use = groups[mask] if groups is not None else None
                if verbose and mask.any():
                    n_after = mask.sum()
                    print(f"\n  peak_shaving_benefit: nur usage_hours <= {PEAK_SHAVING_USAGE_HOURS_MAX} (n={n_after})")
        # Pro-Target Feature-Set: zuerst aus artifacts/features/<target>/selected_feature_list.txt, sonst config
        allowed_cols = _get_feature_list_for_target(target)
        if allowed_cols is None and FEATURE_SETS_PER_TARGET:
            allowed_cols = FEATURE_SETS_PER_TARGET.get(target)
        if allowed_cols:
            existing = [c for c in allowed_cols if c in X_use.columns]
            missing = set(allowed_cols) - set(existing)
            if verbose:
                src = "selected_feature_list.txt" if (ARTIFACTS_FEATURES_DIR / _target_to_feature_subfolder(target) / "selected_feature_list.txt").exists() else "config"
                print(f"\n  {target}: {len(existing)} Features (Quelle: {src})")
            if missing and verbose:
                print(f"      {len(missing)} konfigurierte Features nicht in Matrix: {list(missing)[:5]}{'…' if len(missing) > 5 else ''}")
            if existing:
                X_use = X_use[existing]
            # wenn keine davon in Matrix, X_use unverändert (alle Features)
        n_with_target = y_use.notna().sum()
        if n_with_target < 5:
            print(f"\nSkipping {target}: not enough data ({n_with_target} non-NaN)")
            continue
        if n_total > 0 and n_with_target < 0.1 * n_total and verbose:
            print(f"\nNote: {target}: only {n_with_target} of {n_total} samples have target (rest NaN). Consider populating this KPI for more configs.")
        try:
            model, metrics, importance = train_single_model(
                X_use, y_use, "target_peak_shaving_benefit" if is_peak_usage_model else target,
                groups=groups_use,
                model_type=model_type,
                verbose=verbose,
                test_clients=test_clients,
                split_seed=split_seed,
            )
            
            hp = {'model_type': type(model).__name__, 'group_aware': groups_use is not None}
            if target == "target_peak_shaving_benefit":
                hp['peak_shaving_usage_hours_max'] = PEAK_SHAVING_USAGE_HOURS_MAX
            if is_peak_usage_model:
                hp['usage_hours_threshold'] = PEAK_USAGE_HOURS_THRESHOLD
                if peak_usage_registry is None:
                    peak_usage_registry = ModelRegistry(registry_dir=MODELS_DIR_PEAK_USAGE)
                peak_usage_registry.register_model(
                    target_name="peak_shaving_benefit",
                    model=model,
                    metrics=metrics,
                    feature_importance=importance,
                    hyperparameters=hp,
                    n_samples=int(y_use.notna().sum()),
                    n_features=X_use.shape[1],
                )
                peak_usage_registry._save_registry()
                if verbose:
                    print(f"  → {MODELS_DIR_PEAK_USAGE}/peak_shaving_benefit_model.joblib")
            else:
                registry.register_model(
                    target_name=target,
                    model=model,
                    metrics=metrics,
                    feature_importance=importance,
                    hyperparameters=hp,
                    n_samples=y_use.notna().sum(),
                    n_features=X_use.shape[1],
                )
            
        except Exception as e:
            print(f"\nError training {target}: {e}")
    
    print("\n" + "="*60)
    print("TRAINING COMPLETE")
    print("="*60)
    n_main = len(registry.models)
    n_peak = len(peak_usage_registry.models) if peak_usage_registry else 0
    print(f"Models trained: {n_main + n_peak}/{len(targets_to_train)}" + (f" (Standard: {n_main}, Sondermodell: {n_peak})" if n_peak else ""))
    
    return registry, peak_usage_registry


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train battery benefit models")
    parser.add_argument(
        "--model", 
        choices=["auto", "xgboost", "gradient_boosting", "ridge"],
        default="auto",
        help="Model type to use"
    )
    parser.add_argument(
        "--no-group-split",
        action="store_true",
        help="Disable group-aware splitting (by default, all runs from one "
             "client stay together in train or test, not both)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )
    parser.add_argument(
        "--test-clients",
        type=str,
        default=None,
        help="Comma-separated client names to use as test set (rest = train). Overrides random group split."
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=42,
        help="Random seed for train/test group split (default: 42)"
    )
    parser.add_argument(
        "--target",
        choices=["1", "2", "3", "peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue"],
        default=None,
        help="Only train this model: 1=peak_shaving_benefit, 2=energy_procurement_optimization, 3=trading_revenue",
    )
    
    args = parser.parse_args()
    
    targets_filter = None
    if args.target:
        _map = {"1": TARGETS[0], "2": TARGETS[1], "3": TARGETS[2],
                "peak_shaving_benefit": TARGETS[0], "energy_procurement_optimization": TARGETS[1], "trading_revenue": TARGETS[2]}
        targets_filter = [_map[args.target]]
    
    test_clients_list = None
    if args.test_clients:
        test_clients_list = [s.strip() for s in args.test_clients.split(",") if s.strip()]
    
    registry, peak_usage_registry = train_all_models(
        model_type=args.model,
        group_aware=not args.no_group_split,
        verbose=not args.quiet,
        test_clients=test_clients_list,
        split_seed=args.split_seed,
        targets_filter=targets_filter,
    )
    
    # Print summary (nur die in diesem Lauf trainierten Targets)
    from .compare_models import print_model_overview
    if targets_filter:
        only_main = [t.replace("target_", "", 1) for t in targets_filter if t != TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS]
        if only_main:
            print_model_overview(registry, only_targets=only_main)
        if TARGET_PEAK_SHAVING_PEAK_USAGE_HOURS in targets_filter and peak_usage_registry is not None:
            print_model_overview(peak_usage_registry, only_targets=["peak_shaving_benefit"])
    else:
        print_model_overview(registry)
