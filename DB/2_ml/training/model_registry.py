"""
Model Registry
==============

Centralized storage and management for all 3 battery benefit models.
Tracks performance metrics, feature importance, and model artifacts.
"""

import json
import pickle
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional

import numpy as np

# Try joblib (faster), fall back to pickle
try:
    import joblib
    USE_JOBLIB = True
except ImportError:
    USE_JOBLIB = False


@dataclass
class ModelInfo:
    """Information about a single trained model."""
    target_name: str
    model_type: str
    r2_score: float
    mae: float
    rmse: float
    cv_r2_mean: float
    cv_r2_std: float
    n_samples: int
    n_features: int
    feature_importance: Dict[str, float]
    hyperparameters: Dict[str, Any]
    training_date: str
    model_path: str


class ModelRegistry:
    """
    Registry for managing multiple target models.
    
    Stores models in the 'models/' directory with a central registry.json
    that tracks all model metadata.
    
    Usage:
        registry = ModelRegistry()
        registry.register_model("peak_shaving_benefit", model, metrics, importance)
        registry.summary()
        registry.compare_features()
        registry.save()
    """
    
    # The 3 target variables we're predicting
    TARGETS = [
        "peak_shaving_benefit",
        "energy_procurement_optimization",
        "trading_revenue"
    ]
    
    def __init__(self, registry_dir: str = "2_ml/artifacts/models"):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(exist_ok=True)
        self.models: Dict[str, ModelInfo] = {}
        self._load_registry()
    
    def _load_registry(self):
        """Load existing registry if it exists."""
        registry_file = self.registry_dir / "registry.json"
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                data = json.load(f)
                for name, info in data.items():
                    self.models[name] = ModelInfo(**info)
    
    def _save_registry(self):
        """Save registry to JSON."""
        registry_file = self.registry_dir / "registry.json"
        data = {name: asdict(info) for name, info in self.models.items()}
        with open(registry_file, 'w') as f:
            json.dump(data, f, indent=2, default=self._json_serialize)
    
    @staticmethod
    def _json_serialize(obj):
        """
        Custom JSON serializer for numpy types.
        
        Python's json module can't handle numpy's int64/float64 types.
        This converts them to native Python types.
        """
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    
    def register_model(
        self,
        target_name: str,
        model,
        metrics: Dict[str, float],
        feature_importance: Dict[str, float],
        hyperparameters: Dict[str, Any] = None,
        n_samples: int = 0,
        n_features: int = 0
    ):
        """
        Register a trained model.
        
        Args:
            target_name: Name of target variable (with or without 'target_' prefix)
            model: Trained sklearn/xgboost model
            metrics: Dict with 'r2', 'mae', 'rmse', 'cv_r2_mean', 'cv_r2_std'
            feature_importance: Dict mapping feature_name -> importance
            hyperparameters: Model hyperparameters
            n_samples: Number of training samples
            n_features: Number of features
        """
        # Clean target name
        clean_name = target_name.replace("target_", "")
        
        # Save model file
        ext = ".joblib" if USE_JOBLIB else ".pkl"
        model_path = str(self.registry_dir / f"{clean_name}_model{ext}")
        
        if USE_JOBLIB:
            joblib.dump(model, model_path)
        else:
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
        
        # Create model info
        self.models[clean_name] = ModelInfo(
            target_name=clean_name,
            model_type=type(model).__name__,
            r2_score=metrics.get('r2', 0),
            mae=metrics.get('mae', 0),
            rmse=metrics.get('rmse', 0),
            cv_r2_mean=metrics.get('cv_r2_mean', 0),
            cv_r2_std=metrics.get('cv_r2_std', 0),
            n_samples=n_samples,
            n_features=n_features,
            feature_importance=feature_importance,
            hyperparameters=hyperparameters or {},
            training_date=datetime.now().isoformat(),
            model_path=model_path
        )
        
        self._save_registry()
        print(f"Registered model: {clean_name}")
    
    def load_model(self, target_name: str):
        """Load a trained model by name."""
        clean_name = target_name.replace("target_", "")
        if clean_name not in self.models:
            raise ValueError(f"Model not found: {clean_name}. Available: {list(self.models.keys())}")
        
        model_path = self.models[clean_name].model_path
        
        if USE_JOBLIB:
            return joblib.load(model_path)
        else:
            with open(model_path, 'rb') as f:
                return pickle.load(f)
    
    def get_model_info(self, target_name: str) -> ModelInfo:
        """Get model info by name."""
        clean_name = target_name.replace("target_", "")
        if clean_name not in self.models:
            raise ValueError(f"Model not found: {clean_name}")
        return self.models[clean_name]
    
    def is_trained(self, target_name: str) -> bool:
        """Check if a model is trained."""
        clean_name = target_name.replace("target_", "")
        return clean_name in self.models
    
    def all_trained(self) -> bool:
        """Check if all 3 models are trained."""
        return all(self.is_trained(t) for t in self.TARGETS)
    
    def list_models(self) -> List[str]:
        """List all registered model names."""
        return list(self.models.keys())
    
    def clear(self):
        """Clear all registered models."""
        for info in self.models.values():
            path = Path(info.model_path)
            if path.exists():
                path.unlink()
        self.models.clear()
        registry_file = self.registry_dir / "registry.json"
        if registry_file.exists():
            registry_file.unlink()
        print("Registry cleared.")
