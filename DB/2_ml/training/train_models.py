"""
Model Training
==============

Train all 3 battery benefit models:
- peak_shaving_benefit
- energy_procurement_optimization
- trading_revenue

Modell-Wahl: Entweder hier per CLI (--model) oder per Aufruf train_all_models(model_type=…).
Optional: default_model aus 2_ml.config (DEFAULT_CONFIG) nutzen, wenn model_type nicht gesetzt ist.

Usage:
    python -m 2_ml.training.train_models

    # Or from Python:
    from 2_ml.training import train_all_models
    train_all_models()

    # Model type via CLI or argument:
    python -m 2_ml.training.train_models --model ridge
    train_all_models(model_type="ridge")
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Any, Optional

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
from .model_registry import ModelRegistry

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


def prepare_data() -> Tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Load and prepare data for training.
    
    Returns:
        X: Feature matrix (imputed)
        df: Full dataframe (for targets)
        feature_names: List of feature column names
    """
    store = FeatureStore()
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
    verbose: bool = True
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
    
    if n_samples < 10:
        raise ValueError(f"Not enough samples for {clean_name}: {n_samples}")
    
    # Determine model type - default to Gradient Boosted Trees
    if model_type == "auto":
        if HAS_XGB and n_samples >= 50:
            model_type = "xgboost"
        else:
            # Always prefer gradient boosting for interpretability with SHAP
            model_type = "gradient_boosting"
    
    # Train/test split - GROUP-AWARE if groups provided
    use_group_split = groups_clean is not None and n_groups >= 2
    
    if use_group_split:
        # Group-aware split: ensures complete clients in train/test
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=42)
        train_idx, test_idx = next(gss.split(X_clean, y_clean, groups_clean))
        
        X_train = X_clean.iloc[train_idx]
        X_test = X_clean.iloc[test_idx]
        y_train = y_clean.iloc[train_idx]
        y_test = y_clean.iloc[test_idx]
        
        if verbose:
            train_clients = sorted(groups_clean.iloc[train_idx].unique())
            test_clients = sorted(groups_clean.iloc[test_idx].unique())
            print(f"Train clients ({len(train_clients)}): {train_clients}")
            print(f"Test clients ({len(test_clients)}): {test_clients}")
    else:
        # Standard random split
        X_train, X_test, y_train, y_test = train_test_split(
            X_clean, y_clean, test_size=test_size, random_state=42
        )
        if verbose and groups_clean is not None:
            print("Not enough groups for group-aware split, using random split")
    
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
        # For Ridge, we need to scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        X_clean_scaled = scaler.transform(X_clean)
        
        model = Ridge(alpha=1.0)
        model.fit(X_train_scaled, y_train)
        
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
    model.fit(X_train, y_train)
    
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
    verbose: bool = True
) -> ModelRegistry:
    """
    Train all 3 target models and register them.
    
    Args:
        model_type: "xgboost", "gradient_boosting", "ridge", or "auto"
        group_aware: If True, ensures clients are not split between train/test.
                     This prevents data leakage when multiple runs exist per client.
        verbose: Print progress
    
    Returns:
        ModelRegistry with all trained models
    """
    print("\n" + "="*60)
    print("TRAINING ALL BATTERY BENEFIT MODELS")
    print("="*60)
    
    # Load data
    X, df, feature_names = prepare_data()
    print(f"Loaded {len(df)} samples with {len(feature_names)} features")
    
    # Get client groups for group-aware splitting
    groups = None
    if group_aware and 'client_name' in df.columns:
        groups = df['client_name']
        n_groups = groups.nunique()
        print(f"Group-aware splitting: {n_groups} unique clients")
        if n_groups < 2:
            print("Only 1 client found - falling back to random splits")
            groups = None
    elif group_aware:
        print("No 'client_name' column found - using random splits")
    
    # Initialize registry
    registry = ModelRegistry()
    
    # Train each model
    for target in TARGETS:
        y = df[target]
        
        if y.notna().sum() < 5:
            print(f"\nSkipping {target}: not enough data")
            continue
        
        try:
            model, metrics, importance = train_single_model(
                X, y, target,
                groups=groups,
                model_type=model_type,
                verbose=verbose
            )
            
            registry.register_model(
                target_name=target,
                model=model,
                metrics=metrics,
                feature_importance=importance,
                hyperparameters={
                    'model_type': type(model).__name__,
                    'group_aware': groups is not None
                },
                n_samples=y.notna().sum(),
                n_features=len(feature_names)
            )
            
        except Exception as e:
            print(f"\nError training {target}: {e}")
    
    print("\n" + "="*60)
    print("TRAINING COMPLETE")
    print("="*60)
    print(f"Models trained: {len(registry.models)}/3")
    
    return registry


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
    
    args = parser.parse_args()
    
    registry = train_all_models(
        model_type=args.model,
        group_aware=not args.no_group_split,
        verbose=not args.quiet
    )
    
    # Print summary
    from .compare_models import print_model_overview
    print_model_overview()
