"""
Feature Extraction Pipeline
============================

Orchestrates the end-to-end feature extraction process.
Loads timeseries one by one, extracts features, saves to local store
and optionally to the database (feature_sets + ml_features).
"""
import json
import numpy as np
import pandas as pd

from .db_utils import connect_with_retry
from typing import Optional, Any, List, Dict

from .data_loader import DuckDBLoader
from .feature_extractors import FeatureExtractorRegistry
from .feature_store import FeatureStore
from .kpi_feature_extractor import KPIFeatureExtractor
from ..config_feature_extraction import (
    KPIFeatureConfig,
    DEFAULT_KPI_CONFIG,
    DIRECT_INPUT_NAMES,
    INDIRECT_INPUT_NAMES,
    INDIRECT_INPUTS_ENABLED,
    LOAD_PROFILE_COLUMN_SPECS,
    LOAD_PROFILE_DF_FEATURE_NAMES,
    RATIO_FEATURES,
)
from .timeseries_aggregations import extract_df_features_only


class FeatureExtractionPipeline:
    """
    End-to-end feature extraction pipeline. Nutzt 2_ml/config_feature_extraction.py.

    Input-Features:
      (a) Exakte KPIs (direct): aus battery_configs / kpi_summary, 1:1 übernommen.
      (b) Indirect (wenn aktiv): aus config, derzeit disabled.
      (c) Berechnete Features (load-profile): aus Zeitreihen-CSVs, Specs in config_feature_extraction.py
          (LOAD_PROFILE_COLUMN_SPECS, LOAD_PROFILE_DF_FEATURE_NAMES).
    Targets: aus kpi_summary (target_kpis aus config).
    """
    
    DEFAULT_FEATURE_SET_NAME = "default"

    def __init__(self,
                 db_path: str = "database/battery_simulations.duckdb",
                 store_dir: str = "2_ml/artifacts/features",
                 data_root: str = "data",
                 kpi_config: KPIFeatureConfig = None,
                 save_to_db: bool = True):
        """
        Initialize the feature extraction pipeline.

        Args:
            db_path: Path to DuckDB database
            store_dir: Directory for storing extracted features
            data_root: Root directory for data files
            kpi_config: Custom KPI feature configuration
            save_to_db: If True (default), also write features to DB (feature_sets + ml_features)
        """
        self.db_path = db_path
        self.save_to_db = save_to_db
        self.loader = DuckDBLoader(db_path, data_root)
        self.store = FeatureStore(store_dir)
        # Nur Config-basierte Features (direct + load-profile aus config_feature_extraction.py).
        self.ts_registry = FeatureExtractorRegistry.config_only()
        self.kpi_extractor = KPIFeatureExtractor(db_path, kpi_config or DEFAULT_KPI_CONFIG)
        self._feature_set_id: Optional[int] = None
    
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
        
        # Always update/create feature_set when saving to DB (so config is current even if 0 configs to process)
        if self.save_to_db:
            self._feature_set_id = self._get_or_create_feature_set()
        
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
            if self.save_to_db:
                print(f"  DB: features → feature_sets + ml_features")

        batch_features = []
        iterator = self.loader.iter_configs_with_timeseries(
            target_kpi, client_filter, skip_ids
        )
        
        # Progress: tqdm advances per config (don't list() – that would load all CSVs first)
        use_tqdm = False
        if verbose:
            try:
                from tqdm import tqdm
                iterator = tqdm(iterator, total=total, desc="Extracting", unit="config")
                use_tqdm = True
            except ImportError:
                print("(Install tqdm for progress bar: pip install tqdm)")
        
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
                # Fehlendes pv_annual_total aus PV-Zeitreihe (Summe) ziehen
                if "pv_annual_total" in DIRECT_INPUT_NAMES:
                    val = row_features.get("pv_annual_total")
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        pv_col = next((c for c in ["pv_load_kwh", "pv_load_0"] if c in ts_df.columns), None)
                        if pv_col is not None:
                            row_features["pv_annual_total"] = float(ts_df[pv_col].sum())
                # Ratio features: numerator (KPI/direct) / sum(timeseries column)
                den_col_candidates = {
                    "pv_load_kwh": ["pv_load_kwh", "pv_load_0"],
                    "consumption_load_kwh": ["consumption_load_kwh", "consumption_load_0", "consumption_kwh"],
                }
                for spec in RATIO_FEATURES:
                    name = spec.get("name")
                    num_key = spec.get("numerator")
                    den_col = spec.get("denominator_sum_column")
                    if not name or not num_key or not den_col:
                        continue
                    num_val = row_features.get(num_key)
                    candidates = den_col_candidates.get(den_col, [den_col])
                    col = next((c for c in candidates if c in ts_df.columns), None)
                    if col is None:
                        row_features[name] = np.nan
                        continue
                    den_val = ts_df[col].sum()
                    if pd.isna(num_val) or den_val is None or den_val == 0:
                        row_features[name] = np.nan
                    else:
                        row_features[name] = float(num_val) / float(den_val)
            
            # Targets aus kpi_summary (keine KPI-Absolute als Input)
            targets = self.kpi_extractor.get_target_values(config_id)
            row_features.update(targets)
            
            # Use primary target from metadata
            row_features["target"] = metadata["target"]
            
            batch_features.append(row_features)
            
            # Progress (when not using tqdm): print every 50 configs
            if verbose and not use_tqdm and (i + 1) % 50 == 0:
                print(f"  [{i + 1}/{total}] config_id={config_id} …", flush=True)
            
            # Save batch periodically (crash recovery)
            if len(batch_features) >= batch_size:
                self._save_batch(batch_features, feature_set_id=self._feature_set_id)
                batch_features = []
                if verbose and not use_tqdm:
                    print(f"  Saved batch ({i + 1}/{total})", flush=True)
        
        # Save final batch
        if batch_features:
            self._save_batch(batch_features, feature_set_id=self._feature_set_id)
        
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
            self._print_computed_features(df)
            if self.save_to_db and self._feature_set_id is not None:
                n_rows = self._get_ml_features_count(self._feature_set_id)
                print(f"  → DB ml_features: {n_rows} rows for feature_set '{self.DEFAULT_FEATURE_SET_NAME}' (upserted/overwritten)")
        
        return self.store.load_features()
    
    def _print_computed_features(self, df: pd.DataFrame) -> None:
        """Print each computed feature name, grouped by type (only when verbose)."""
        if df.empty:
            print("  Features computed: (none – no configs processed)")
            return
        cols = list(df.columns)
        meta = {"config_id", "client_name", "run_name", "config_name"}
        direct = [c for c in cols if c in DIRECT_INPUT_NAMES]
        ts_features = [c for c in cols if c.startswith("ts__")]
        ratio_names = [s["name"] for s in RATIO_FEATURES]
        ratio = [c for c in cols if c in ratio_names]
        target_cols = [c for c in cols if c == "target" or (isinstance(c, str) and c.startswith("target_"))]
        other = [c for c in cols if c not in meta and c not in direct and c not in ts_features and c not in ratio and c not in target_cols]

        print("  Features computed:")
        for label, names in [
            ("direct", sorted(direct)),
            ("ts__ (load-profile)", sorted(ts_features)),
            ("ratio", sorted(ratio)),
            ("target", sorted(target_cols)),
            ("other", sorted(other)),
        ]:
            if names:
                print(f"    [{label}]")
                for n in names:
                    print(f"      {n}")

    def _get_ml_features_count(self, feature_set_id: int) -> int:
        """Return number of rows in ml_features for the given feature_set_id."""
        with connect_with_retry(self.db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM ml_features WHERE feature_set_id = ?",
                [feature_set_id],
            ).fetchone()
            return int(row[0]) if row else 0

    def _save_batch(self, batch_features: list, feature_set_id: Optional[int] = None):
        """Save a batch of features to the store and optionally to the DB."""
        batch_df = pd.DataFrame(batch_features)
        self.store.append_features(batch_df)
        if self.save_to_db and feature_set_id is not None:
            self._save_batch_to_db(batch_features, feature_set_id)

    def _ensure_updated_at_column(self, conn) -> None:
        """Add updated_at to feature_sets if missing (for existing DBs)."""
        try:
            conn.execute("ALTER TABLE feature_sets ADD COLUMN updated_at TIMESTAMP")
        except Exception:
            pass  # Column already exists

    def _get_or_create_feature_set(self) -> int:
        """Ensure feature_sets has a row for current config; return feature_set_id."""
        feature_config: dict[str, Any] = {
            "direct_input_names": list(DIRECT_INPUT_NAMES),
            "load_profile_column_specs": LOAD_PROFILE_COLUMN_SPECS,
            "load_profile_df_feature_names": list(LOAD_PROFILE_DF_FEATURE_NAMES),
            "ratio_features": list(RATIO_FEATURES),
        }
        if INDIRECT_INPUTS_ENABLED:
            feature_config["indirect_input_names"] = list(INDIRECT_INPUT_NAMES)
        config_json = json.dumps(feature_config)
        description = "From config_feature_extraction (direct + load-profile-derived)"

        with connect_with_retry(self.db_path, read_only=False) as conn:
            row = conn.execute(
                "SELECT feature_set_id FROM feature_sets WHERE feature_set_name = ?",
                [self.DEFAULT_FEATURE_SET_NAME],
            ).fetchone()
            if row:
                self._ensure_updated_at_column(conn)
                conn.execute(
                    """
                    UPDATE feature_sets
                    SET feature_config = ?::JSON, description = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE feature_set_name = ?
                    """,
                    [config_json, description, self.DEFAULT_FEATURE_SET_NAME],
                )
                return int(row[0])
            conn.execute(
                """
                INSERT INTO feature_sets (feature_set_name, description, feature_config, target_columns)
                VALUES (?, ?, ?::JSON, ?::JSON)
                """,
                [
                    self.DEFAULT_FEATURE_SET_NAME,
                    description,
                    config_json,
                    json.dumps([]),
                ],
            )
            row = conn.execute(
                "SELECT feature_set_id FROM feature_sets WHERE feature_set_name = ?",
                [self.DEFAULT_FEATURE_SET_NAME],
            ).fetchone()
            return int(row[0])

    def _row_to_features_dict(self, row: dict) -> dict:
        """Build input-feature dict only (no IDs, no target/target_*)."""
        exclude = {"config_id", "client_name", "run_name", "config_name", "target"}
        features = {}
        for k, v in row.items():
            if k in exclude or (isinstance(k, str) and k.startswith("target_")):
                continue
            if pd.isna(v):
                features[k] = None
            elif hasattr(v, "item"):
                features[k] = v.item()
            else:
                features[k] = v
        return features

    def _save_batch_to_db(self, batch_features: list, feature_set_id: int):
        """Write batch to ml_features (upsert: overwrite existing rows for same config_id + feature_set_id)."""
        with connect_with_retry(self.db_path, read_only=False) as conn:
            for row in batch_features:
                config_id = int(row["config_id"])  # native int for reliable DB match
                features = self._row_to_features_dict(row)
                features_json = json.dumps(features)
                feature_count = len(features)
                conn.execute(
                    """
                    INSERT INTO ml_features (config_id, feature_set_id, features, feature_count, extraction_time_ms)
                    VALUES (?, ?, ?::JSON, ?, 0)
                    ON CONFLICT (config_id, feature_set_id)
                    DO UPDATE SET
                        features = EXCLUDED.features,
                        feature_count = EXCLUDED.feature_count,
                        extraction_time_ms = EXCLUDED.extraction_time_ms
                    """,
                    [config_id, feature_set_id, features_json, feature_count],
                )

    def reset(self):
        """Clear all stored features and start fresh (file store + DB ml_features for default set)."""
        self.store.clear()
        self.kpi_extractor.clear_cache()
        if self.save_to_db:
            with connect_with_retry(self.db_path, read_only=False) as conn:
                row = conn.execute(
                    "SELECT feature_set_id FROM feature_sets WHERE feature_set_name = ?",
                    [self.DEFAULT_FEATURE_SET_NAME],
                ).fetchone()
                if row:
                    conn.execute("DELETE FROM ml_features WHERE feature_set_id = ?", [row[0]])
        print("Feature store cleared.")

    def refresh_targets_only(self, verbose: bool = True) -> pd.DataFrame:
        """
        Update only the target_* columns in the existing feature matrix from kpi_summary.
        Does not re-extract input features; use after calculate_benefit_targets.py.
        """
        df = self.store.load_features()
        if df.empty:
            if verbose:
                print("No feature matrix found. Run full extraction first.")
            return df
        if "config_id" not in df.columns:
            if verbose:
                print("Feature matrix has no config_id. Run full extraction first.")
            return df

        target_kpi_names = list(self.kpi_extractor.config.target_kpis)
        if not target_kpi_names:
            if verbose:
                print("No target KPIs configured.")
            return df

        config_ids = df["config_id"].astype(int).tolist()
        placeholders = ",".join("?" * len(config_ids))
        kpi_placeholders = ",".join("?" * len(target_kpi_names))
        with connect_with_retry(self.db_path, read_only=True) as conn:
            result = conn.execute(
                f"""
                SELECT config_id, kpi_name, kpi_value
                FROM kpi_summary
                WHERE config_id IN ({placeholders})
                  AND kpi_name IN ({kpi_placeholders})
                """,
                config_ids + target_kpi_names,
            ).df()

        if result.empty:
            if verbose:
                print("No target KPIs found in kpi_summary for these config_ids.")
            return df

        # Pivot: one row per config_id, columns target_peak_shaving_benefit, ...
        pivot = result.pivot(index="config_id", columns="kpi_name", values="kpi_value")
        pivot.columns = [f"target_{c}" for c in pivot.columns]

        # Drop existing target columns from df, merge new targets
        drop_cols = [c for c in df.columns if c == "target" or (isinstance(c, str) and c.startswith("target_"))]
        df = df.drop(columns=drop_cols, errors="ignore")
        df = df.merge(pivot, left_on="config_id", right_index=True, how="left")
        # Primary target column (e.g. for backward compatibility)
        first_target = f"target_{target_kpi_names[0]}"
        if first_target in df.columns:
            df["target"] = df[first_target]

        self.store.save_features(df)
        if verbose:
            n_updated = pivot.shape[0]
            print(f"Refreshed target columns from kpi_summary for {n_updated} configs. Saved to {self.store.store_dir}/")
        return df

    def run_only_features(
        self,
        feature_names: List[str],
        target_kpi: str = "peak_shaving_benefit",
        client_filter: Optional[str] = None,
        verbose: bool = True,
    ) -> pd.DataFrame:
        """
        Extrahiert nur die angegebenen load-profile-Features (z.B. ts__usage_hours) und
        ersetzt/ergänzt die entsprechenden Spalten in der bestehenden Feature-Matrix.
        Keine Voll-Extraktion – nur Zeitreihen laden und die gewünschten CUSTOM_DF_FEATURES
        berechnen (z.B. usage_hours). Nützlich nach Config-Änderung oder fehlender Spalte.

        feature_names: Namen mit oder ohne Prefix, z.B. ["ts__usage_hours"] oder ["usage_hours"].
        Es werden nur CUSTOM_DF_FEATURES aus LOAD_PROFILE_DF_FEATURE_NAMES unterstützt.
        """
        # Normalisieren: "ts__usage_hours" / "usage_hours" -> base "usage_hours", matrix-Spalte "ts__usage_hours"
        TS_PREFIX = "ts__"
        base_to_matrix: Dict[str, str] = {}
        for name in feature_names:
            name = (name or "").strip()
            if not name:
                continue
            base = name[len(TS_PREFIX):] if name.startswith(TS_PREFIX) else name
            base_to_matrix[base] = TS_PREFIX + base
        if not base_to_matrix:
            if verbose:
                print("No valid feature names given.")
            return self.store.load_features()

        base_names = list(base_to_matrix.keys())
        matrix_cols = list(base_to_matrix.values())

        df = self.store.load_features()
        if df.empty or "config_id" not in df.columns:
            if verbose:
                print("No feature matrix found. Run full extraction first: python 2_ml/1_extract_features.py")
            return df

        config_ids = set(df["config_id"].astype(int))
        for col in matrix_cols:
            if col not in df.columns:
                df[col] = np.nan

        iterator = self.loader.iter_configs_with_timeseries(
            target_kpi, client_filter, skip_config_ids=None
        )
        if verbose:
            try:
                from tqdm import tqdm
                total = self.loader.get_config_count(target_kpi, client_filter, skip_config_ids=None)
                iterator = tqdm(iterator, total=total, desc="Only-features", unit="config")
            except ImportError:
                pass

        updated = 0
        for metadata, ts_df in iterator:
            config_id = int(metadata["config_id"])
            if config_id not in config_ids:
                continue
            if ts_df.empty:
                for col in matrix_cols:
                    df.loc[df["config_id"] == config_id, col] = np.nan
                continue
            values = extract_df_features_only(ts_df, base_names)
            for base, matrix_col in base_to_matrix.items():
                val = values.get(base, np.nan)
                df.loc[df["config_id"] == config_id, matrix_col] = val
            updated += 1

        self.store.save_features(df)
        self.store.save_metadata(
            extractor_config={"only_features_run": matrix_cols},
            target_kpi=target_kpi,
        )
        if verbose:
            print(f"Updated {updated} configs. Columns: {matrix_cols}")
            print(f"Saved to {self.store.store_dir}/")
        return df

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
