"""
Feature Extraction Pipeline
============================

Orchestrates the end-to-end feature extraction process.
Loads timeseries one by one, extracts features, saves to local store.
"""
import pandas as pd
from typing import Optional

from .data_loader import DuckDBLoader
from .feature_extractors import FeatureExtractorRegistry
from .feature_store import FeatureStore
from .kpi_feature_extractor import KPIFeatureExtractor
from ..config import (
    KPIFeatureConfig,
    DEFAULT_KPI_CONFIG,
    DIRECT_INPUT_NAMES,
    INDIRECT_INPUT_NAMES,
    INDIRECT_INPUTS_ENABLED,
)


class FeatureExtractionPipeline:
    """
    End-to-end feature extraction pipeline.
    Input-Features aus: (a) direct inputs, (b) indirect inputs (wenn aktiv),
    (c) load-profile-derived. Targets aus kpi_summary (target_kpis).
    """
    
    def __init__(self,
                 db_path: str = "database/battery_simulations.duckdb",
                 store_dir: str = "2_ml/artifacts/features",
                 data_root: str = "data",
                 kpi_config: KPIFeatureConfig = None):
        """
        Initialize the feature extraction pipeline.
        
        Args:
            db_path: Path to DuckDB database
            store_dir: Directory for storing extracted features
            data_root: Root directory for data files
            kpi_config: Custom KPI feature configuration
        """
        self.db_path = db_path
        self.loader = DuckDBLoader(db_path, data_root)
        self.store = FeatureStore(store_dir)
        # Nur Config-basierte Features (direct + load-profile aus config.py).
        # Keine Legacy-Extractoren (LoadProfileFeatures, BatteryFeatures, TemporalFeatures, GridFeatures).
        self.ts_registry = FeatureExtractorRegistry.config_only()
        self.kpi_extractor = KPIFeatureExtractor(db_path, kpi_config or DEFAULT_KPI_CONFIG)
    
    def run(self,
            target_kpi: str = "peak_shaving_benefit",
            client_filter: Optional[str] = None,
            incremental: bool = True,
            batch_size: int = 50,
            include_timeseries_features: bool = True,
            verbose: bool = True) -> pd.DataFrame:
        """
        Run the feature extraction pipeline.
        
        Input-Features: direct (Metadata), ggf. indirect, load-profile-derived.
        Targets: aus kpi_summary (target_kpis). Keine KPI-Absolute als Input.
        
        Args:
            target_kpi: Main KPI to use as target variable
            client_filter: Optional client name to filter
            incremental: If True, skip already processed configs
            batch_size: Save to disk every N configs (for crash recovery)
            include_timeseries_features: Extract load-profile-derived features from timeseries
            verbose: Show progress
        
        Returns:
            Complete feature DataFrame
        """
        # Validate target KPIs
        if verbose:
            validation = self.kpi_extractor.validate_config()
            if validation['missing']:
                missing_preview = validation['missing'][:5]
                print(f"Missing target KPIs (will be NaN): {missing_preview}...")
        
        # Get configs to skip if incremental
        skip_ids = self.store.get_processed_configs() if incremental else set()
        
        # Get total count (no skip) to distinguish "DB leer" vs "alles schon verarbeitet"
        total_in_db = self.loader.get_config_count(target_kpi, client_filter, skip_config_ids=None)
        total = self.loader.get_config_count(target_kpi, client_filter, skip_ids)
        
        if total == 0:
            if verbose:
                if total_in_db == 0:
                    print("Keine Configs in der DB (oder target_kpi/client_filter trifft nichts).")
                    print(f"  DB: {self.db_path}  |  Prüfe: battery_configs + kpi_summary.")
                else:
                    print(f"No new configs to process (alle {total_in_db} bereits in processed_configs).")
                    print("  Neu bauen: python 2_ml/1_extract_features.py --reset --no-incremental")
            # Trotzdem Metadaten und feature_list.txt schreiben (ggf. leer)
            self.store.save_metadata(
                extractor_config={
                    "input_sources": ["direct", "load_profile"] + (["indirect"] if INDIRECT_INPUTS_ENABLED else []),
                    "ts_extractors": [e.name for e in self.ts_registry.extractors],
                    "target_kpis": self.kpi_extractor.config.target_kpis,
                },
                target_kpi=target_kpi
            )
            return self.store.load_features()
        
        if verbose:
            print(f"Processing {total} battery configurations...")
            print(f"  Input sources: direct, {'indirect, ' if INDIRECT_INPUTS_ENABLED else ''}load-profile-derived")
            print(f"  Load-profile features: {'on' if include_timeseries_features else 'off'}")
        
        batch_features = []
        iterator = self.loader.iter_configs_with_timeseries(
            target_kpi, client_filter, skip_ids
        )
        
        # Try to use tqdm for progress bar if available
        try:
            from tqdm import tqdm
            if verbose:
                iterator = tqdm(list(iterator), total=total, desc="Extracting features")
        except ImportError:
            if verbose:
                print("(Install tqdm for progress bar: pip install tqdm)")
            iterator = list(iterator)
        
        for i, (metadata, ts_df) in enumerate(iterator):
            config_id = metadata["config_id"]
            
            # Identifiers + direct inputs (from config)
            row_features = {
                "config_id": config_id,
                "client_name": metadata["client_name"],
                "run_name": metadata["run_name"],
                "config_name": metadata["config_name"],
            }
            for key in DIRECT_INPUT_NAMES:
                if key in metadata:
                    row_features[key] = metadata[key]
            # Direkte Inputs aus kpi_summary (KPI-Namen aus den KPI-Sheets)
            missing_direct = [k for k in DIRECT_INPUT_NAMES if k not in row_features]
            if missing_direct:
                kpi_inputs = self.kpi_extractor.get_kpi_values(config_id, missing_direct)
                row_features.update(kpi_inputs)
            if INDIRECT_INPUTS_ENABLED:
                for key in INDIRECT_INPUT_NAMES:
                    if key in metadata:
                        row_features[key] = metadata[key]
            
            # Load-profile-derived features (from timeseries)
            if include_timeseries_features and not ts_df.empty:
                ts_features = self.ts_registry.extract_all(ts_df)
                row_features.update(ts_features)
            
            # Targets aus kpi_summary (keine KPI-Absolute als Input)
            targets = self.kpi_extractor.get_target_values(config_id)
            row_features.update(targets)
            
            # Use primary target from metadata
            row_features["target"] = metadata["target"]
            
            batch_features.append(row_features)
            
            # Save batch periodically (crash recovery)
            if len(batch_features) >= batch_size:
                self._save_batch(batch_features)
                batch_features = []
                if verbose and not hasattr(iterator, '__iter__'):
                    print(f"  Saved batch... ({i+1}/{total})")
        
        # Save final batch
        if batch_features:
            self._save_batch(batch_features)
        
        # Save metadata
        input_sources = ["direct", "load_profile"]
        if INDIRECT_INPUTS_ENABLED:
            input_sources.insert(1, "indirect")
        self.store.save_metadata(
            extractor_config={
                "input_sources": input_sources,
                "ts_extractors": [e.name for e in self.ts_registry.extractors],
                "target_kpis": self.kpi_extractor.config.target_kpis,
            },
            target_kpi=target_kpi
        )
        
        if verbose:
            df = self.store.load_features()
            print(f"Extracted {len(df.columns)} features for {len(df)} configs")
            print(f"Saved to {self.store.store_dir}/")
        
        return self.store.load_features()
    
    def _save_batch(self, batch_features: list):
        """Save a batch of features to the store."""
        batch_df = pd.DataFrame(batch_features)
        self.store.append_features(batch_df)
    
    def reset(self):
        """Clear all stored features and start fresh."""
        self.store.clear()
        self.kpi_extractor.clear_cache()
        print("Feature store cleared.")
    
    def get_training_data(self, target_col: str = "target"):
        """Get X, y ready for sklearn."""
        return self.store.get_ml_ready_data(target_col=target_col)
    
    def describe(self):
        """Print summary of the feature store."""
        info = self.store.describe()
        
        print("\n" + "="*50)
        print("FEATURE STORE SUMMARY")
        print("="*50)
        print(f"Status: {info['status']}")
        print(f"Configurations: {info['num_configs']}")
        print(f"Total features: {info['num_features']}")
        print(f"  - Load-profile-derived: {info.get('timeseries_features', 0)}")
        print(f"  - Target features: {info.get('target_features', 0)}")
        
        if info.get('metadata'):
            print(f"\nLast updated: {info['metadata'].get('last_updated', 'N/A')}")
            print(f"Target KPI: {info['metadata'].get('target_kpi', 'N/A')}")
        print("="*50)


# Convenience function
def extract_features(target_kpi: str = "peak_shaving_benefit", 
                     incremental: bool = True,
                     **kwargs) -> pd.DataFrame:
    """
    Quick function to run feature extraction.
    
    Args:
        target_kpi: Main KPI to use as target variable
        incremental: If True, skip already processed configs
        **kwargs: Additional arguments for FeatureExtractionPipeline
    
    Returns:
        DataFrame with extracted features
    """
    pipeline = FeatureExtractionPipeline(**kwargs)
    return pipeline.run(target_kpi=target_kpi, incremental=incremental)


# =============================================================================
# CLI (für Workflow: python -m 2_ml.extraction.pipeline)
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract ML features from battery DB")
    parser.add_argument(
        "--target-kpi",
        default="peak_shaving_benefit",
        help="Target KPI (default: peak_shaving_benefit)"
    )
    parser.add_argument("--no-incremental", action="store_true", help="Re-run all configs")
    parser.add_argument("-c", "--client", help="Filter by client name")
    parser.add_argument("--quiet", action="store_true", help="Less output")
    args = parser.parse_args()
    pipeline = FeatureExtractionPipeline()
    df = pipeline.run(
        target_kpi=args.target_kpi,
        incremental=not args.no_incremental,
        client_filter=args.client or None,
        verbose=not args.quiet,
    )
    print(f"\n✅ Features: {len(df)} Zeilen, {len(df.columns)} Spalten → 2_ml/artifacts/features/")
