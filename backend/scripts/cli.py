#!/usr/bin/env python3
"""
Battery Database CLI
====================
Command-line interface for managing the battery simulation database.

Usage:
    python cli.py init                              # Initialize database
    python cli.py add-client <name>                 # Add a new client
    python cli.py add-run <client> <run>            # Add a new run
    python cli.py import <path>                     # Import from folder structure
    python cli.py list [clients|runs|configs]       # List items
    python cli.py query <sql>                       # Run custom SQL
    python cli.py summary                           # Show database summary
    python cli.py compare <client> <run> [kpi]      # Compare configs in a run
    
    # ML Features & Training
    python cli.py extract-features                  # Extract ML features
    python cli.py list-features                     # List extracted feature sets
    python cli.py train <target_kpi>                # Train ML model
    python cli.py compare-models <target_kpi>       # Compare model types
    python cli.py list-kpis                         # List available KPIs
    python cli.py list-models                       # List trained models
    
    # Benefit Calculation (derived outcome variables)
    python cli.py calculate-benefits --save         # Calculate and save benefits
    python cli.py list-benefits                     # List benefit definitions
"""

import argparse
import sys
from pathlib import Path
from tabulate import tabulate
from battery_db import BatteryDatabase


def cmd_init(args):
    """Initialize the database."""
    with BatteryDatabase() as db:
        print("✅ Database initialized successfully!")
        print(f"   Database file: {db.db_path}")
        print(f"   Data folder: {db.data_root}")


def cmd_add_client(args):
    """Add a new client."""
    with BatteryDatabase() as db:
        client_id = db.add_client(args.name, args.description)
        print(f"✅ Client '{args.name}' added/exists with ID: {client_id}")


def cmd_add_run(args):
    """Add a new run."""
    import json
    
    params = None
    if args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON for parameters: {args.params}")
            return
    
    with BatteryDatabase() as db:
        run_id = db.add_run(
            client_name=args.client,
            run_name=args.run,
            run_description=args.description,
            input_parameters=params
        )
        print(f"✅ Run '{args.run}' added/exists with ID: {run_id}")
        print(f"   Folder created at: data/{db._sanitize_name(args.client)}/{db._sanitize_name(args.run)}/")


def cmd_add_config(args):
    """Add a battery configuration."""
    with BatteryDatabase() as db:
        config_id = db.add_battery_config(
            client_name=args.client,
            run_name=args.run,
            config_name=args.config,
            is_baseline=args.baseline,
            battery_capacity_kwh=args.capacity,
            battery_power_kw=args.power,
            battery_efficiency=args.efficiency,
            kpi_file=args.kpi_file,
            timeseries_file=args.ts_file
        )
        print(f"✅ Config '{args.config}' added/exists with ID: {config_id}")


def cmd_import(args):
    """Import from existing folder structure."""
    with BatteryDatabase() as db:
        print(f"🔍 Scanning folder: {args.path or 'data/'}")
        db.scan_and_import_folder(args.path)
        print("\n✅ Import complete!")
        db.summary()


def cmd_list(args):
    """List items in the database."""
    with BatteryDatabase() as db:
        if args.type == "clients":
            df = db.get_clients()
            print("\n📁 CLIENTS:")
        elif args.type == "runs":
            df = db.get_runs(args.filter)
            print(f"\n📊 RUNS{' for ' + args.filter if args.filter else ''}:")
        elif args.type == "configs":
            df = db.get_battery_configs(args.filter)
            print(f"\n🔋 CONFIGS{' for ' + args.filter if args.filter else ''}:")
        else:
            print(f"Unknown type: {args.type}")
            return
        
        if df.empty:
            print("   No items found.")
        else:
            print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))


def cmd_query(args):
    """Run a custom SQL query."""
    with BatteryDatabase() as db:
        try:
            df = db.execute(args.sql)
            print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
        except Exception as e:
            print(f"❌ Query error: {e}")


def cmd_summary(args):
    """Show database summary."""
    with BatteryDatabase() as db:
        db.summary()


def cmd_compare(args):
    """Compare configurations within a run."""
    with BatteryDatabase() as db:
        df = db.compare_configs(args.client, args.run, args.kpi)
        
        if df.empty:
            print(f"No data found for {args.client}/{args.run}")
            return
        
        print(f"\n📊 Comparison: {args.client} / {args.run}")
        if args.kpi:
            print(f"   KPI: {args.kpi}\n")
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))


def cmd_view_timeseries(args):
    """View timeseries data from CSV."""
    with BatteryDatabase() as db:
        df = db.query_timeseries_csv(args.client, args.run, args.config)
        
        if df.empty:
            print("No timeseries data found.")
            return
        
        print(f"\n📈 Timeseries: {args.client}/{args.run}/{args.config}")
        print(f"   Shape: {df.shape[0]} rows × {df.shape[1]} columns")
        print(f"   Columns: {', '.join(df.columns)}\n")
        
        if args.head:
            print(tabulate(df.head(args.head), headers='keys', tablefmt='psql', showindex=False))
        else:
            print(tabulate(df.head(10), headers='keys', tablefmt='psql', showindex=False))
            if len(df) > 10:
                print(f"   ... and {len(df) - 10} more rows")


def cmd_export(args):
    """Export query results to CSV."""
    with BatteryDatabase() as db:
        try:
            df = db.execute(args.sql)
            df.to_csv(args.output, index=False)
            print(f"✅ Exported {len(df)} rows to {args.output}")
        except Exception as e:
            print(f"❌ Export error: {e}")


# =========================================================================
# ML Feature Extraction & Training Commands
# =========================================================================

def cmd_extract_features(args):
    """Extract ML features from timeseries data."""
    from feature_engineering import FeatureExtractor, FeatureConfig
    
    with BatteryDatabase() as db:
        # Build config from args
        config_kwargs = {}
        if args.rolling_windows:
            config_kwargs['rolling_windows'] = [int(w) for w in args.rolling_windows.split(',')]
        if args.fourier_periods:
            config_kwargs['fourier_periods'] = [int(p) for p in args.fourier_periods.split(',')]
        config_kwargs['include_fourier'] = not args.no_fourier
        config_kwargs['include_peak_features'] = not args.no_peak
        
        config = FeatureConfig(**config_kwargs)
        extractor = FeatureExtractor(db, config)
        
        print(f"\n🔧 Extracting features...")
        print(f"   Feature set: {args.feature_set}")
        if args.client:
            print(f"   Client filter: {args.client}")
        
        features_df = extractor.build_feature_matrix(
            client_name=args.client,
            save_to_db=True,
            feature_set_name=args.feature_set
        )
        
        if len(features_df) > 0:
            # Count feature types
            from feature_engineering import get_feature_names
            feature_cols = get_feature_names(features_df)
            
            categories = {}
            for col in feature_cols:
                prefix = col.split('_')[0]
                categories[prefix] = categories.get(prefix, 0) + 1
            
            print(f"\n✅ Extracted {len(feature_cols)} features for {len(features_df)} configurations")
            print(f"\n   Feature categories:")
            for cat, count in sorted(categories.items()):
                print(f"     {cat}: {count} features")
        else:
            print("⚠️  No features extracted. Check that timeseries files exist.")


def cmd_list_features(args):
    """List extracted feature sets."""
    with BatteryDatabase() as db:
        df = db.execute("""
            SELECT 
                fs.feature_set_name,
                fs.description,
                COUNT(mf.ml_feature_id) as num_configs,
                MAX(mf.feature_count) as num_features,
                MAX(mf.created_at) as last_updated
            FROM feature_sets fs
            LEFT JOIN ml_features mf ON fs.feature_set_id = mf.feature_set_id
            GROUP BY fs.feature_set_id, fs.feature_set_name, fs.description
            ORDER BY fs.created_at DESC
        """)
        
        print("\n📊 FEATURE SETS:")
        if df.empty:
            print("   No feature sets found. Run 'extract-features' first.")
        else:
            print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))


def cmd_list_kpis(args):
    """List available KPIs that can be used as training targets."""
    with BatteryDatabase() as db:
        df = db.execute("""
            SELECT 
                kpi_name,
                COUNT(DISTINCT config_id) as num_configs,
                AVG(kpi_value) as avg_value,
                MIN(kpi_value) as min_value,
                MAX(kpi_value) as max_value
            FROM kpi_summary
            GROUP BY kpi_name
            ORDER BY kpi_name
        """)
        
        print("\n📈 AVAILABLE KPIs:")
        if df.empty:
            print("   No KPIs found. Import data first.")
        else:
            print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))


def cmd_train(args):
    """Train an ML model."""
    try:
        from ml_pipeline import MLPipeline, TrainingConfig
    except ImportError as e:
        print(f"❌ ML dependencies not available: {e}")
        print("   Install with: pip install scikit-learn")
        return
    
    with BatteryDatabase() as db:
        pipeline = MLPipeline(db)
        
        # Build training config
        config = TrainingConfig(
            test_size=args.test_size,
            cv_folds=args.cv_folds,
            hyperparameter_search=args.grid_search
        )
        
        try:
            result = pipeline.train(
                target_kpi=args.target_kpi,
                model_type=args.model_type,
                feature_set_name=args.feature_set,
                config=config,
                client_name=args.client,
                model_name=args.model_name
            )
            
            print(f"\n✅ Model saved as: {result.model_name}")
            
            # Export feature importance if requested
            if args.export_importance and result.feature_importance:
                import pandas as pd
                imp_df = pd.DataFrame([
                    {'feature': k, 'importance': v}
                    for k, v in result.feature_importance.items()
                ]).sort_values('importance', ascending=False)
                imp_df.to_csv(args.export_importance, index=False)
                print(f"   Feature importance exported to: {args.export_importance}")
                
        except Exception as e:
            print(f"❌ Training error: {e}")
            import traceback
            traceback.print_exc()


def cmd_compare_models(args):
    """Compare different model types."""
    try:
        from ml_pipeline import MLPipeline, TrainingConfig
    except ImportError as e:
        print(f"❌ ML dependencies not available: {e}")
        print("   Install with: pip install scikit-learn")
        return
    
    with BatteryDatabase() as db:
        pipeline = MLPipeline(db)
        
        model_types = args.model_types.split(',') if args.model_types else None
        
        config = TrainingConfig(
            test_size=args.test_size,
            cv_folds=args.cv_folds
        )
        
        try:
            comparison_df = pipeline.compare_models(
                target_kpi=args.target_kpi,
                model_types=model_types,
                feature_set_name=args.feature_set,
                config=config
            )
            
            if args.output:
                comparison_df.to_csv(args.output, index=False)
                print(f"\n📁 Results saved to: {args.output}")
                
        except Exception as e:
            print(f"❌ Comparison error: {e}")
            import traceback
            traceback.print_exc()


def cmd_list_models(args):
    """List trained models."""
    with BatteryDatabase() as db:
        df = db.execute("""
            SELECT 
                model_name,
                model_type,
                target_kpi,
                json_extract(metrics, '$.test_r2') as test_r2,
                json_extract(metrics, '$.test_rmse') as test_rmse,
                created_at
            FROM ml_models
            ORDER BY created_at DESC
        """)
        
        print("\n🤖 TRAINED MODELS:")
        if df.empty:
            print("   No models found. Run 'train' first.")
        else:
            print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))


def cmd_predict(args):
    """Make predictions with a trained model."""
    try:
        from ml_pipeline import MLPipeline
    except ImportError as e:
        print(f"❌ ML dependencies not available: {e}")
        return
    
    with BatteryDatabase() as db:
        pipeline = MLPipeline(db)
        
        config_ids = None
        if args.config_ids:
            config_ids = [int(x) for x in args.config_ids.split(',')]
        
        try:
            predictions = pipeline.predict(
                model_name=args.model_name,
                config_ids=config_ids,
                feature_set_name=args.feature_set
            )
            
            print("\n📊 PREDICTIONS:")
            print(tabulate(predictions, headers='keys', tablefmt='psql', showindex=False))
            
            if args.output:
                predictions.to_csv(args.output, index=False)
                print(f"\n📁 Predictions saved to: {args.output}")
                
        except Exception as e:
            print(f"❌ Prediction error: {e}")


def cmd_feature_correlations(args):
    """Show correlations between features and a target KPI."""
    try:
        from ml_pipeline import FeatureSelector
    except ImportError as e:
        print(f"❌ ML dependencies not available: {e}")
        return
    
    with BatteryDatabase() as db:
        selector = FeatureSelector(db)
        
        try:
            corr_df = selector.get_feature_kpi_correlations(
                target_kpi=args.target_kpi,
                feature_set_name=args.feature_set
            )
            
            if len(corr_df) == 0:
                print("No correlations found. Extract features first.")
                return
            
            print(f"\n📊 Top {args.top} Features Correlated with '{args.target_kpi}':")
            print(tabulate(
                corr_df.head(args.top), 
                headers='keys', 
                tablefmt='psql', 
                showindex=False
            ))
            
            if args.output:
                corr_df.to_csv(args.output, index=False)
                print(f"\n📁 Full correlations saved to: {args.output}")
                
        except Exception as e:
            print(f"❌ Correlation error: {e}")


# =========================================================================
# Benefit Calculation Commands
# =========================================================================

def cmd_calculate_benefits(args):
    """Calculate benefit KPIs relative to baseline."""
    from benefit_calculator import BenefitCalculator
    
    with BatteryDatabase() as db:
        calc = BenefitCalculator(db)
        
        print("\n📊 Calculating benefits relative to 0-battery baseline...")
        
        if args.client and args.run:
            benefits_df = calc.calculate_benefits_for_run(
                args.client, args.run,
                include_baseline=args.include_baseline
            )
        else:
            benefits_df = calc.calculate_all_benefits(
                client_name=args.client,
                include_baseline=args.include_baseline
            )
        
        if len(benefits_df) == 0:
            print("⚠️  No benefits calculated. Check that baseline cases exist.")
            return
        
        # Show summary
        summary = calc.get_benefit_summary(benefits_df)
        print("\n=== Benefit Summary ===")
        print(tabulate(summary, headers='keys', tablefmt='psql', showindex=False))
        
        # Save to database if requested
        if args.save:
            print("\n💾 Saving benefits to database as KPIs...")
            calc.save_benefits_as_kpis(benefits_df)
        
        # Export to CSV if requested
        if args.output:
            benefits_df.to_csv(args.output, index=False)
            print(f"\n📁 Benefits exported to: {args.output}")
        
        print(f"\n✅ Calculated benefits for {len(benefits_df)} battery configurations")


def cmd_list_benefits(args):
    """List available benefit definitions."""
    from benefit_calculator import BENEFIT_DEFINITIONS
    
    print("\n📊 AVAILABLE BENEFIT DEFINITIONS:")
    rows = []
    for name, defn in BENEFIT_DEFINITIONS.items():
        # Handle both simple and composite benefits
        if defn.get('is_composite', False):
            source_kpi = ' + '.join(defn.get('component_kpis', []))
        else:
            source_kpi = defn.get('baseline_kpi', 'N/A')
        
        rows.append({
            'benefit_name': name,
            'source_kpi(s)': source_kpi,
            'calculation': defn['calculation'],
            'unit': defn['unit']
        })
    
    print(tabulate(rows, headers='keys', tablefmt='psql', showindex=False))
    
    print("\nUsage:")
    print("  python cli.py calculate-benefits --save    # Calculate and save to DB")


def main():
    parser = argparse.ArgumentParser(
        description="Battery Simulation Database CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # init
    subparsers.add_parser('init', help='Initialize the database')
    
    # add-client
    p = subparsers.add_parser('add-client', help='Add a new client')
    p.add_argument('name', help='Client name')
    p.add_argument('-d', '--description', help='Client description')
    
    # add-run
    p = subparsers.add_parser('add-run', help='Add a new run')
    p.add_argument('client', help='Client name')
    p.add_argument('run', help='Run name')
    p.add_argument('-d', '--description', help='Run description')
    p.add_argument('-p', '--params', help='Input parameters as JSON string')
    
    # add-config
    p = subparsers.add_parser('add-config', help='Add a battery configuration')
    p.add_argument('client', help='Client name')
    p.add_argument('run', help='Run name')
    p.add_argument('config', help='Configuration name')
    p.add_argument('--baseline', action='store_true', help='Mark as baseline (0 battery)')
    p.add_argument('--capacity', type=float, help='Battery capacity (kWh)')
    p.add_argument('--power', type=float, help='Battery power (kW)')
    p.add_argument('--efficiency', type=float, help='Round-trip efficiency (0-1)')
    p.add_argument('--kpi-file', help='KPI summary CSV filename')
    p.add_argument('--ts-file', help='Timeseries CSV filename')
    
    # import
    p = subparsers.add_parser('import', help='Import from folder structure')
    p.add_argument('path', nargs='?', help='Root path to import from (default: data/)')
    
    # list
    p = subparsers.add_parser('list', help='List items')
    p.add_argument('type', choices=['clients', 'runs', 'configs'], help='What to list')
    p.add_argument('-f', '--filter', help='Filter by client name')
    
    # query
    p = subparsers.add_parser('query', help='Run a custom SQL query')
    p.add_argument('sql', help='SQL query to execute')
    
    # summary
    subparsers.add_parser('summary', help='Show database summary')
    
    # compare
    p = subparsers.add_parser('compare', help='Compare configs within a run')
    p.add_argument('client', help='Client name')
    p.add_argument('run', help='Run name')
    p.add_argument('kpi', nargs='?', help='Specific KPI to compare')
    
    # view-ts
    p = subparsers.add_parser('view-ts', help='View timeseries data')
    p.add_argument('client', help='Client name')
    p.add_argument('run', help='Run name')
    p.add_argument('config', help='Configuration name')
    p.add_argument('--head', type=int, help='Number of rows to show')
    
    # export
    p = subparsers.add_parser('export', help='Export query results to CSV')
    p.add_argument('sql', help='SQL query to execute')
    p.add_argument('-o', '--output', required=True, help='Output CSV file')
    
    # =========================================================================
    # ML Feature Extraction & Training Commands
    # =========================================================================
    
    # extract-features
    p = subparsers.add_parser('extract-features', help='Extract ML features from timeseries')
    p.add_argument('-f', '--feature-set', default='default', help='Feature set name')
    p.add_argument('-c', '--client', help='Filter by client name')
    p.add_argument('--rolling-windows', help='Rolling window sizes (comma-separated, e.g., "4,24,96")')
    p.add_argument('--fourier-periods', help='Fourier periods (comma-separated)')
    p.add_argument('--no-fourier', action='store_true', help='Disable Fourier features')
    p.add_argument('--no-peak', action='store_true', help='Disable peak window features')
    
    # list-features
    subparsers.add_parser('list-features', help='List extracted feature sets')
    
    # list-kpis
    subparsers.add_parser('list-kpis', help='List available KPIs for training')
    
    # train
    p = subparsers.add_parser('train', help='Train an ML model')
    p.add_argument('target_kpi', help='Target KPI to predict')
    p.add_argument('-m', '--model-type', default='random_forest',
                   choices=['ridge', 'lasso', 'elastic_net', 'random_forest', 
                           'gradient_boosting', 'xgboost'],
                   help='Model type to train')
    p.add_argument('-f', '--feature-set', default='default', help='Feature set to use')
    p.add_argument('-c', '--client', help='Filter by client name')
    p.add_argument('--model-name', help='Custom name for the model')
    p.add_argument('--test-size', type=float, default=0.2, help='Test set fraction')
    p.add_argument('--cv-folds', type=int, default=5, help='Cross-validation folds')
    p.add_argument('--grid-search', action='store_true', help='Enable hyperparameter grid search')
    p.add_argument('--export-importance', help='Export feature importance to CSV file')
    
    # compare-models
    p = subparsers.add_parser('compare-models', help='Compare different model types')
    p.add_argument('target_kpi', help='Target KPI to predict')
    p.add_argument('-t', '--model-types', help='Model types to compare (comma-separated)')
    p.add_argument('-f', '--feature-set', default='default', help='Feature set to use')
    p.add_argument('--test-size', type=float, default=0.2, help='Test set fraction')
    p.add_argument('--cv-folds', type=int, default=5, help='Cross-validation folds')
    p.add_argument('-o', '--output', help='Output CSV file for comparison results')
    
    # list-models
    subparsers.add_parser('list-models', help='List trained models')
    
    # predict
    p = subparsers.add_parser('predict', help='Make predictions with a trained model')
    p.add_argument('model_name', help='Name of the model to use')
    p.add_argument('-f', '--feature-set', default='default', help='Feature set to use')
    p.add_argument('--config-ids', help='Specific config IDs (comma-separated)')
    p.add_argument('-o', '--output', help='Output CSV file for predictions')
    
    # feature-correlations
    p = subparsers.add_parser('feature-correlations', help='Show feature-KPI correlations')
    p.add_argument('target_kpi', help='Target KPI')
    p.add_argument('-f', '--feature-set', default='default', help='Feature set to use')
    p.add_argument('--top', type=int, default=20, help='Number of top features to show')
    p.add_argument('-o', '--output', help='Output CSV file for all correlations')
    
    # =========================================================================
    # Benefit Calculation Commands
    # =========================================================================
    
    # calculate-benefits
    p = subparsers.add_parser('calculate-benefits', 
                              help='Calculate benefit KPIs relative to 0-battery baseline')
    p.add_argument('-c', '--client', help='Filter by client name')
    p.add_argument('-r', '--run', help='Filter by run name (requires --client)')
    p.add_argument('--save', action='store_true', help='Save benefits to database as KPIs')
    p.add_argument('--include-baseline', action='store_true', 
                   help='Include baseline cases (with 0 benefits)')
    p.add_argument('-o', '--output', help='Export benefits to CSV file')
    
    # list-benefits
    subparsers.add_parser('list-benefits', help='List available benefit definitions')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Route to command handler
    commands = {
        'init': cmd_init,
        'add-client': cmd_add_client,
        'add-run': cmd_add_run,
        'add-config': cmd_add_config,
        'import': cmd_import,
        'list': cmd_list,
        'query': cmd_query,
        'summary': cmd_summary,
        'compare': cmd_compare,
        'view-ts': cmd_view_timeseries,
        'export': cmd_export,
        # ML commands
        'extract-features': cmd_extract_features,
        'list-features': cmd_list_features,
        'list-kpis': cmd_list_kpis,
        'train': cmd_train,
        'compare-models': cmd_compare_models,
        'list-models': cmd_list_models,
        'predict': cmd_predict,
        'feature-correlations': cmd_feature_correlations,
        # Benefit calculation commands
        'calculate-benefits': cmd_calculate_benefits,
        'list-benefits': cmd_list_benefits,
    }
    
    commands[args.command](args)


if __name__ == "__main__":
    main()

