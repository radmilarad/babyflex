"""
Model Training & Evaluation
============================

Tools for training, evaluating, and comparing battery benefit models.

Targets:
    - peak_shaving_benefit
    - energy_procurement_optimization
    - trading_revenue

Quick Start:
    # Train all models
    python -m 2_ml.training.train_models

    # Evaluate models
    python -m 2_ml.training.evaluate_models

    # Compare models
    python -m 2_ml.training.compare_models

Programmatic Usage:
    from 2_ml.training import ModelRegistry, train_all_models, compare_models
    train_all_models()
    compare_models()
"""

from .model_registry import ModelRegistry, ModelInfo
from .train_models import train_all_models, train_single_model, prepare_data
from .evaluate_models import (
    evaluate_models,
    predict,
    explain_model,
    compute_shap_values,
    feature_importance_shap,
    compare_feature_effects,
)
from .compare_models import compare_models, print_model_overview

__all__ = [
    "ModelRegistry",
    "ModelInfo",
    "train_all_models",
    "train_single_model",
    "prepare_data",
    "evaluate_models",
    "predict",
    "explain_model",
    "compute_shap_values",
    "feature_importance_shap",
    "compare_feature_effects",
    "compare_models",
    "print_model_overview",
]
