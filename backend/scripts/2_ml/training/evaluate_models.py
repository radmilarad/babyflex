"""
Model Evaluation
================

Evaluate trained models on new data or generate predictions.
Includes comprehensive SHAP-based model interpretability.

Usage:
    python -m 2_ml.training.evaluate_models

    # Or from Python:
    from 2_ml.training.evaluate_models import evaluate_models, predict, explain_model
    # or via package:
    from 2_ml.training import evaluate_models, predict, explain_model
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from sklearn.impute import SimpleImputer

from .. import FeatureStore
from .model_registry import ModelRegistry


def evaluate_models(
    registry: ModelRegistry = None,
    X: pd.DataFrame = None,
    y_dict: Dict[str, pd.Series] = None,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Evaluate all models on provided data.
    
    Args:
        registry: ModelRegistry instance
        X: Feature matrix (uses stored features if None)
        y_dict: Dict mapping target_name -> Series (uses stored if None)
        verbose: Print results
    
    Returns:
        DataFrame with evaluation metrics per model
    """
    if registry is None:
        registry = ModelRegistry()
    
    if not registry.models:
        print("No models found. Run training first.")
        return pd.DataFrame()
    
    # Load data if not provided
    if X is None or y_dict is None:
        store = FeatureStore()
        df = store.load_features()
        
        exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
        exclude.update([f"target_{t}" for t in registry.TARGETS])
        feature_cols = [c for c in df.columns if c not in exclude]
        
        X = df[feature_cols]
        
        # Impute
        imputer = SimpleImputer(strategy='median')
        X = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
        
        y_dict = {f"target_{t}": df[f"target_{t}"] for t in registry.TARGETS if f"target_{t}" in df.columns}
    
    results = []
    
    if verbose:
        print("\n" + "="*60)
        print("MODEL EVALUATION")
        print("="*60)
    
    for name, info in registry.models.items():
        target_col = f"target_{name}"
        
        if target_col not in y_dict:
            if verbose:
                print(f"\nNo target data for {name}")
            continue
        
        y = y_dict[target_col]
        mask = ~y.isna()
        X_eval = X[mask]
        y_eval = y[mask]
        
        if len(y_eval) == 0:
            continue
        
        # Load model and predict
        model = registry.load_model(name)
        y_pred = model.predict(X_eval)
        
        # Calculate metrics
        r2 = r2_score(y_eval, y_pred)
        mae = mean_absolute_error(y_eval, y_pred)
        rmse = np.sqrt(mean_squared_error(y_eval, y_pred))
        
        results.append({
            'model': name,
            'n_samples': len(y_eval),
            'r2': r2,
            'mae': mae,
            'rmse': rmse,
            'mean_actual': y_eval.mean(),
            'mean_predicted': y_pred.mean(),
        })
        
        if verbose:
            print(f"\n--- {name} ---")
            print(f"  Samples: {len(y_eval)}")
            print(f"  R²: {r2:.3f}")
            print(f"  MAE: {mae:.2f}")
            print(f"  RMSE: {rmse:.2f}")
            print(f"  Mean actual: {y_eval.mean():.2f}")
            print(f"  Mean predicted: {y_pred.mean():.2f}")
    
    return pd.DataFrame(results)


def predict(
    X: pd.DataFrame,
    target_names: List[str] = None,
    registry: ModelRegistry = None
) -> pd.DataFrame:
    """
    Generate predictions for all or specific targets.
    
    Args:
        X: Feature matrix (must have same columns as training data)
        target_names: List of targets to predict (all if None)
        registry: ModelRegistry instance
    
    Returns:
        DataFrame with predictions for each target
    """
    if registry is None:
        registry = ModelRegistry()
    
    if target_names is None:
        target_names = list(registry.models.keys())
    
    predictions = pd.DataFrame(index=X.index)
    
    for name in target_names:
        clean_name = name.replace("target_", "")
        
        if clean_name not in registry.models:
            print(f"Model not found: {clean_name}")
            continue
        
        model = registry.load_model(clean_name)
        predictions[f"pred_{clean_name}"] = model.predict(X)
    
    return predictions


def get_prediction_with_confidence(
    X: pd.DataFrame,
    target_name: str,
    registry: ModelRegistry = None,
    n_estimators_sample: int = 50
) -> pd.DataFrame:
    """
    Get predictions with confidence intervals (for tree-based models).
    Uses individual tree predictions to estimate uncertainty.
    """
    if registry is None:
        registry = ModelRegistry()
    
    clean_name = target_name.replace("target_", "")
    model = registry.load_model(clean_name)
    
    # Main prediction
    y_pred = model.predict(X)
    
    results = pd.DataFrame(index=X.index)
    results['prediction'] = y_pred
    
    # Try to get uncertainty from tree models
    if hasattr(model, 'estimators_'):
        n_trees = min(n_estimators_sample, len(model.estimators_))
        tree_preds = np.array([
            tree[0].predict(X) if hasattr(tree, '__len__') else tree.predict(X)
            for tree in model.estimators_[:n_trees]
        ])
        
        results['std'] = tree_preds.std(axis=0)
        results['lower_bound'] = results['prediction'] - 1.96 * results['std']
        results['upper_bound'] = results['prediction'] + 1.96 * results['std']
    
    return results


# =============================================================================
# SHAP-BASED MODEL INTERPRETABILITY
# =============================================================================

def _get_shap_explainer(model, X: pd.DataFrame):
    """Create appropriate SHAP explainer based on model type."""
    import shap
    
    model_type = type(model).__name__
    
    if model_type in ['GradientBoostingRegressor', 'RandomForestRegressor', 
                      'XGBRegressor', 'LGBMRegressor', 'CatBoostRegressor']:
        return shap.TreeExplainer(model)
    
    if hasattr(model, 'get_booster'):
        return shap.TreeExplainer(model)
    
    if hasattr(model, 'coef_'):
        background = shap.sample(X, min(100, len(X)))
        return shap.LinearExplainer(model, background)
    
    background = shap.sample(X, min(50, len(X)))
    return shap.KernelExplainer(model.predict, background)


def compute_shap_values(
    X: pd.DataFrame,
    target_name: str,
    registry: ModelRegistry = None
) -> Tuple[np.ndarray, Any]:
    """Compute SHAP values for all samples."""
    try:
        import shap
    except ImportError:
        raise ImportError("Install shap: pip install shap")
    
    if registry is None:
        registry = ModelRegistry()
    
    clean_name = target_name.replace("target_", "")
    model = registry.load_model(clean_name)
    
    explainer = _get_shap_explainer(model, X)
    shap_values = explainer.shap_values(X)
    
    return shap_values, explainer


def feature_importance_shap(
    X: pd.DataFrame,
    target_name: str,
    registry: ModelRegistry = None,
    top_n: int = 15
) -> pd.DataFrame:
    """Calculate feature importance based on mean absolute SHAP values."""
    shap_values, _ = compute_shap_values(X, target_name, registry)
    
    importance = np.abs(shap_values).mean(axis=0)
    
    df = pd.DataFrame({
        'feature': X.columns,
        'mean_abs_shap': importance,
        'std_shap': np.abs(shap_values).std(axis=0),
        'rank': range(1, len(X.columns) + 1)
    })
    
    df = df.sort_values('mean_abs_shap', ascending=False)
    df['rank'] = range(1, len(df) + 1)
    
    return df.head(top_n).reset_index(drop=True)


def feature_contribution(
    X: pd.DataFrame,
    target_name: str,
    registry: ModelRegistry = None
) -> pd.DataFrame:
    """Calculate feature contributions to predictions using SHAP."""
    shap_values, _ = compute_shap_values(X, target_name, registry)
    return pd.DataFrame(shap_values, columns=X.columns, index=X.index)


def explain_prediction(
    X: pd.DataFrame,
    target_name: str,
    sample_idx: int = 0,
    registry: ModelRegistry = None,
    top_n: int = 10
) -> Dict[str, Any]:
    """Explain a single prediction with SHAP values."""
    try:
        import shap
    except ImportError:
        raise ImportError("Install shap: pip install shap")
    
    if registry is None:
        registry = ModelRegistry()
    
    clean_name = target_name.replace("target_", "")
    model = registry.load_model(clean_name)
    
    explainer = _get_shap_explainer(model, X)
    shap_values = explainer.shap_values(X)
    
    if hasattr(explainer, 'expected_value'):
        base_value = explainer.expected_value
        if isinstance(base_value, np.ndarray):
            base_value = base_value[0]
    else:
        base_value = model.predict(X).mean()
    
    sample_shap = shap_values[sample_idx]
    sample_features = X.iloc[sample_idx]
    prediction = model.predict(X.iloc[[sample_idx]])[0]
    
    abs_shap = np.abs(sample_shap)
    top_indices = np.argsort(abs_shap)[-top_n:][::-1]
    
    contributions = []
    for idx in top_indices:
        contributions.append({
            'feature': X.columns[idx],
            'value': sample_features.iloc[idx],
            'shap_value': sample_shap[idx],
            'direction': 'positive' if sample_shap[idx] > 0 else 'negative'
        })
    
    return {
        'base_value': base_value,
        'prediction': prediction,
        'contributions': contributions,
        'sample_index': sample_idx
    }


def explain_model(
    target_name: str,
    registry: ModelRegistry = None,
    save_plots: bool = True,
    output_dir: str = "2_ml/artifacts/shap",
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Comprehensive model explanation using SHAP.
    Generates global feature importance, direction, interactions, and summary.
    """
    try:
        import shap
    except ImportError:
        raise ImportError("Install shap: pip install shap")
    
    if registry is None:
        registry = ModelRegistry()
    
    # Load data
    store = FeatureStore()
    df = store.load_features()
    
    exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
    exclude.update([f"target_{t}" for t in registry.TARGETS])
    feature_cols = [c for c in df.columns if c not in exclude]
    
    X = df[feature_cols]
    imputer = SimpleImputer(strategy='median')
    X = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
    
    clean_name = target_name.replace("target_", "")
    model = registry.load_model(clean_name)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"SHAP ANALYSIS: {clean_name}")
        print(f"{'='*60}")
    
    explainer = _get_shap_explainer(model, X)
    shap_values = explainer.shap_values(X)
    
    if hasattr(explainer, 'expected_value'):
        base_value = explainer.expected_value
        if isinstance(base_value, np.ndarray):
            base_value = float(base_value[0])
    else:
        base_value = float(model.predict(X).mean())
    
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'mean_abs_shap': mean_abs_shap,
        'std_shap': np.abs(shap_values).std(axis=0),
    }).sort_values('mean_abs_shap', ascending=False)
    
    mean_shap = shap_values.mean(axis=0)
    feature_direction = pd.DataFrame({
        'feature': X.columns,
        'mean_shap': mean_shap,
        'effect': ['positive' if v > 0 else 'negative' for v in mean_shap]
    }).sort_values('mean_shap', key=abs, ascending=False)
    
    if verbose:
        print(f"\nBase value (expected prediction): {base_value:.2f}")
        print(f"\nTop 10 Most Important Features (by mean |SHAP|):")
        print("-" * 50)
        for i, row in feature_importance.head(10).iterrows():
            print(f"  {row['feature']:40s}: {row['mean_abs_shap']:.4f}")
    
    if save_plots:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            plt.figure(figsize=(10, 8))
            shap.summary_plot(shap_values, X, plot_type="bar", show=False, max_display=15)
            plt.tight_layout()
            plt.savefig(output_path / f"{clean_name}_shap_importance.png", dpi=150, bbox_inches='tight')
            plt.close()
            
            plt.figure(figsize=(10, 8))
            shap.summary_plot(shap_values, X, show=False, max_display=15)
            plt.tight_layout()
            plt.savefig(output_path / f"{clean_name}_shap_summary.png", dpi=150, bbox_inches='tight')
            plt.close()
            
            if verbose:
                print(f"\nSHAP plots saved to {output_path}/")
        except Exception as e:
            if verbose:
                print(f"\nCould not save plots: {e}")
    
    interaction_effects = {}
    top_features = feature_importance.head(5)['feature'].tolist()
    
    for feat in top_features:
        feat_idx = X.columns.get_loc(feat)
        correlation = np.corrcoef(X[feat], shap_values[:, feat_idx])[0, 1]
        interaction_effects[feat] = {
            'correlation_with_shap': correlation,
            'effect_type': 'linear_positive' if correlation > 0.5 else 
                          ('linear_negative' if correlation < -0.5 else 'nonlinear')
        }
    
    return {
        'target': clean_name,
        'base_value': base_value,
        'n_samples': len(X),
        'n_features': len(X.columns),
        'feature_importance': feature_importance.to_dict('records'),
        'feature_direction': feature_direction.head(15).to_dict('records'),
        'interaction_effects': interaction_effects,
        'shap_values': shap_values,
        'explainer': explainer
    }


def compare_feature_effects(
    registry: ModelRegistry = None,
    top_n: int = 10
) -> pd.DataFrame:
    """Compare feature effects across all trained models."""
    if registry is None:
        registry = ModelRegistry()
    
    store = FeatureStore()
    df = store.load_features()
    
    exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
    exclude.update([f"target_{t}" for t in registry.TARGETS])
    feature_cols = [c for c in df.columns if c not in exclude]
    
    X = df[feature_cols]
    imputer = SimpleImputer(strategy='median')
    X = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
    
    all_results = []
    
    for name in registry.models.keys():
        try:
            shap_values, _ = compute_shap_values(X, name, registry)
            mean_abs_shap = np.abs(shap_values).mean(axis=0)
            mean_shap = shap_values.mean(axis=0)
            
            for i, feat in enumerate(X.columns):
                all_results.append({
                    'target': name,
                    'feature': feat,
                    'mean_abs_shap': mean_abs_shap[i],
                    'mean_shap': mean_shap[i],
                    'direction': 'positive' if mean_shap[i] > 0 else 'negative'
                })
        except Exception as e:
            print(f"Could not compute SHAP for {name}: {e}")
    
    if not all_results:
        return pd.DataFrame()
    
    results_df = pd.DataFrame(all_results)
    pivot_df = results_df.pivot_table(
        index='feature',
        columns='target',
        values='mean_abs_shap',
        aggfunc='mean'
    )
    pivot_df['total_importance'] = pivot_df.sum(axis=1)
    pivot_df = pivot_df.sort_values('total_importance', ascending=False)
    
    return pivot_df.head(top_n)


def get_feature_dependence(
    feature_name: str,
    target_name: str,
    registry: ModelRegistry = None,
    interaction_feature: str = None
) -> pd.DataFrame:
    """Get feature dependence data for a specific feature."""
    if registry is None:
        registry = ModelRegistry()
    
    store = FeatureStore()
    df = store.load_features()
    
    exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
    exclude.update([f"target_{t}" for t in registry.TARGETS])
    feature_cols = [c for c in df.columns if c not in exclude]
    
    X = df[feature_cols]
    imputer = SimpleImputer(strategy='median')
    X = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
    
    if feature_name not in X.columns:
        raise ValueError(f"Feature '{feature_name}' not found. Available: {list(X.columns)}")
    
    shap_values, _ = compute_shap_values(X, target_name, registry)
    feat_idx = X.columns.get_loc(feature_name)
    
    result = pd.DataFrame({
        'feature_value': X[feature_name].values,
        'shap_value': shap_values[:, feat_idx]
    })
    
    if interaction_feature and interaction_feature in X.columns:
        result['interaction_value'] = X[interaction_feature].values
    
    return result


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate battery benefit models")
    parser.add_argument("--shap", action="store_true", help="Run SHAP analysis")
    parser.add_argument(
        "--target",
        choices=["peak_shaving_benefit", "energy_procurement_optimization", "trading_revenue", "all"],
        default="all",
        help="Target model to analyze"
    )
    parser.add_argument("--save-plots", action="store_true", help="Save SHAP plots to outputs/shap/")
    
    args = parser.parse_args()
    
    results = evaluate_models(verbose=True)
    
    if not results.empty:
        print("\n" + "="*60)
        print("EVALUATION SUMMARY")
        print("="*60)
        print(results.to_string(index=False))
    
    if args.shap:
        registry = ModelRegistry()
        
        if args.target == "all":
            targets = list(registry.models.keys())
        else:
            targets = [args.target]
        
        for target in targets:
            if target in registry.models:
                try:
                    explain_model(target, registry=registry, save_plots=args.save_plots, verbose=True)
                except Exception as e:
                    print(f"\nSHAP analysis failed for {target}: {e}")
        
        print("\n" + "="*60)
        print("FEATURE IMPORTANCE ACROSS ALL MODELS")
        print("="*60)
        try:
            comparison = compare_feature_effects(registry)
            if not comparison.empty:
                print(comparison.to_string())
        except Exception as e:
            print(f"Could not compare features: {e}")
