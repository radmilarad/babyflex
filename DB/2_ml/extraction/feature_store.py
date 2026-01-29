"""
Local Feature Storage
=====================

Uses Parquet files for efficient columnar storage.
Supports incremental updates and version tracking.
"""
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple


class FeatureStore:
    """
    Local storage for extracted features.
    Uses Parquet for efficient columnar storage.
    """
    
    def __init__(self, store_dir: str = "2_ml/artifacts/features"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        
        self.features_file = self.store_dir / "feature_matrix.parquet"
        self.metadata_file = self.store_dir / "metadata.json"
        self.processed_file = self.store_dir / "processed_configs.json"
    
    def load_features(self) -> pd.DataFrame:
        """Load existing feature matrix."""
        if self.features_file.exists():
            return pd.read_parquet(self.features_file)
        return pd.DataFrame()
    
    def save_features(self, df: pd.DataFrame):
        """Save feature matrix to Parquet."""
        df.to_parquet(self.features_file, index=False)
    
    def get_processed_configs(self) -> set:
        """Get set of already processed config_ids."""
        if self.processed_file.exists():
            with open(self.processed_file, "r") as f:
                return set(json.load(f))
        return set()
    
    def mark_processed(self, config_ids: list):
        """Mark config_ids as processed."""
        processed = self.get_processed_configs()
        processed.update(config_ids)
        with open(self.processed_file, "w") as f:
            json.dump(list(processed), f)
    
    def append_features(self, new_features: pd.DataFrame):
        """Append new features to existing store."""
        existing = self.load_features()
        
        if existing.empty:
            combined = new_features
        else:
            # Remove any existing rows for these config_ids (for updates)
            if "config_id" in existing.columns and "config_id" in new_features.columns:
                existing = existing[~existing["config_id"].isin(new_features["config_id"])]
            combined = pd.concat([existing, new_features], ignore_index=True)
        
        self.save_features(combined)
        
        if "config_id" in new_features.columns:
            self.mark_processed(new_features["config_id"].tolist())
    
    def save_metadata(self, extractor_config: Dict[str, Any], 
                      target_kpi: str, 
                      extraction_version: str = "1.0"):
        """Save extraction metadata for reproducibility."""
        df = self.load_features()
        # Nur Spalten, die als ML-Input gelten (keine IDs, kein target/target_*)
        exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
        feature_columns = [c for c in df.columns 
                          if c not in exclude and not c.startswith("target_")]
        metadata = {
            "extraction_version": extraction_version,
            "target_kpi": target_kpi,
            "extractor_config": extractor_config,
            "last_updated": datetime.now().isoformat(),
            "feature_count": len(df.columns),
            "feature_columns": sorted(feature_columns),
            "num_input_features": len(feature_columns),
        }
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        # Liste aller Input-Features in eine Textdatei (zum schnellen Nachschauen)
        list_file = self.store_dir / "feature_list.txt"
        with open(list_file, "w") as f:
            f.write("# ML-Input-Features (ohne IDs und Targets)\n")
            for c in sorted(feature_columns):
                f.write(c + "\n")
    
    def load_metadata(self) -> Optional[Dict[str, Any]]:
        """Load extraction metadata."""
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        return None
    
    def clear(self):
        """Clear all stored features (for reprocessing)."""
        if self.features_file.exists():
            self.features_file.unlink()
        if self.processed_file.exists():
            self.processed_file.unlink()
        if self.metadata_file.exists():
            self.metadata_file.unlink()
        list_file = self.store_dir / "feature_list.txt"
        if list_file.exists():
            list_file.unlink()

    def get_ml_ready_data(self, 
                          target_col: str = "target",
                          exclude_cols: list = None) -> Tuple[pd.DataFrame, pd.Series, list]:
        """
        Get X, y ready for sklearn.
        
        Args:
            target_col: Name of target column
            exclude_cols: Additional columns to exclude from features
        
        Returns:
            (X DataFrame, y Series, feature_names list)
        """
        df = self.load_features()
        
        if df.empty:
            raise ValueError("No features in store. Run pipeline first.")
        
        exclude = {"config_id", "client_name", "run_name", "config_name", target_col}
        if exclude_cols:
            exclude.update(exclude_cols)
        
        feature_cols = [c for c in df.columns if c not in exclude]
        
        X = df[feature_cols]
        y = df[target_col] if target_col in df.columns else None
        
        return X, y, feature_cols
    
    def describe(self) -> Dict[str, Any]:
        """Get summary statistics about the feature store."""
        df = self.load_features()
        metadata = self.load_metadata()
        
        if df.empty:
            return {"status": "empty", "num_configs": 0, "num_features": 0}
        
        # Feature types (ohne KPI/delta-Begriffe)
        load_profile_features = [c for c in df.columns if c.startswith("ts__")]
        direct_like = [c for c in df.columns if c.startswith("list_battery_") or c in ("pv_annual_total", "pv_consumed_percentage")]
        target_features = [c for c in df.columns if c.startswith("target_")]
        
        return {
            "status": "ready",
            "num_configs": len(df),
            "num_features": len(df.columns),
            "load_profile_features": len(load_profile_features),
            "direct_input_features": len(direct_like),
            "target_features": len(target_features),
            "metadata": metadata,
        }
