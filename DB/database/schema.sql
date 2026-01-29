-- Battery Simulation Database Schema
-- ===================================

-- Create sequences for auto-incrementing IDs
CREATE SEQUENCE IF NOT EXISTS seq_client_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_run_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_config_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_kpi_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_ts_id START 1;

-- Clients table: stores client information
CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY DEFAULT nextval('seq_client_id'),
    client_name VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Runs table: stores simulation run metadata
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY DEFAULT nextval('seq_run_id'),
    client_id INTEGER NOT NULL REFERENCES clients(client_id),
    run_name VARCHAR NOT NULL,
    run_description VARCHAR,
    run_date TIMESTAMP,
    input_parameters JSON,  -- Flexible storage for all input params
    folder_path VARCHAR,    -- Relative path to the run folder
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, run_name)
);

-- Battery configurations table: stores each battery scenario
CREATE TABLE IF NOT EXISTS battery_configs (
    config_id INTEGER PRIMARY KEY DEFAULT nextval('seq_config_id'),
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    config_name VARCHAR NOT NULL,           -- e.g., "0_battery", "100kWh_50kW"
    is_baseline BOOLEAN DEFAULT FALSE,      -- True for 0-battery case
    battery_capacity_kwh DOUBLE,
    battery_power_kw DOUBLE,
    battery_efficiency DOUBLE,
    other_params JSON,                      -- Flexible storage for additional params
    kpi_file_path VARCHAR,                  -- Path to kpi_summary CSV
    timeseries_file_path VARCHAR,           -- Path to flex_timeseries CSV
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, config_name)
);

-- KPI Summary table: denormalized KPI data for fast querying
CREATE TABLE IF NOT EXISTS kpi_summary (
    kpi_id INTEGER PRIMARY KEY DEFAULT nextval('seq_kpi_id'),
    config_id INTEGER NOT NULL REFERENCES battery_configs(config_id),
    kpi_name VARCHAR NOT NULL,
    kpi_value DOUBLE,
    kpi_unit VARCHAR,
    UNIQUE(config_id, kpi_name)
);

-- Timeseries data table: stores actual timeseries data
-- This is optional - you can query CSVs directly with DuckDB if preferred
CREATE TABLE IF NOT EXISTS flex_timeseries (
    id INTEGER PRIMARY KEY DEFAULT nextval('seq_ts_id'),
    config_id INTEGER NOT NULL REFERENCES battery_configs(config_id),
    timestamp TIMESTAMP NOT NULL,
    soc_percent DOUBLE,              -- State of charge
    power_kw DOUBLE,                 -- Battery power (+ charge, - discharge)
    grid_import_kwh DOUBLE,
    grid_export_kwh DOUBLE,
    load_kwh DOUBLE,
    generation_kwh DOUBLE,
    -- Add more columns as needed based on your CSV structure
    UNIQUE(config_id, timestamp)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_client ON runs(client_id);
CREATE INDEX IF NOT EXISTS idx_configs_run ON battery_configs(run_id);
CREATE INDEX IF NOT EXISTS idx_kpi_config ON kpi_summary(config_id);
CREATE INDEX IF NOT EXISTS idx_timeseries_config ON flex_timeseries(config_id);
CREATE INDEX IF NOT EXISTS idx_timeseries_timestamp ON flex_timeseries(timestamp);

-- Useful views
CREATE OR REPLACE VIEW v_full_hierarchy AS
SELECT 
    c.client_name,
    r.run_name,
    r.run_date,
    r.input_parameters,
    bc.config_name,
    bc.is_baseline,
    bc.battery_capacity_kwh,
    bc.battery_power_kw,
    bc.kpi_file_path,
    bc.timeseries_file_path
FROM clients c
JOIN runs r ON c.client_id = r.client_id
JOIN battery_configs bc ON r.run_id = bc.run_id
ORDER BY c.client_name, r.run_name, bc.config_name;

-- View for comparing battery configs within a run
CREATE OR REPLACE VIEW v_kpi_comparison AS
SELECT 
    c.client_name,
    r.run_name,
    bc.config_name,
    bc.battery_capacity_kwh,
    bc.battery_power_kw,
    kpi.kpi_name,
    kpi.kpi_value,
    kpi.kpi_unit
FROM clients c
JOIN runs r ON c.client_id = r.client_id
JOIN battery_configs bc ON r.run_id = bc.run_id
JOIN kpi_summary kpi ON bc.config_id = kpi.config_id
ORDER BY c.client_name, r.run_name, kpi.kpi_name, bc.battery_capacity_kwh;

-- =========================================================================
-- ML Feature Engineering Tables
-- =========================================================================

-- Sequences for ML tables
CREATE SEQUENCE IF NOT EXISTS seq_feature_set_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_ml_feature_id START 1;
CREATE SEQUENCE IF NOT EXISTS seq_ml_model_id START 1;

-- Feature sets: defines a collection of feature extraction settings
CREATE TABLE IF NOT EXISTS feature_sets (
    feature_set_id INTEGER PRIMARY KEY DEFAULT nextval('seq_feature_set_id'),
    feature_set_name VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    feature_config JSON,          -- Feature extraction configuration
    target_columns JSON,          -- Which timeseries columns to use
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ML Features: stores extracted features per battery config
CREATE TABLE IF NOT EXISTS ml_features (
    ml_feature_id INTEGER PRIMARY KEY DEFAULT nextval('seq_ml_feature_id'),
    config_id INTEGER NOT NULL REFERENCES battery_configs(config_id),
    feature_set_id INTEGER NOT NULL REFERENCES feature_sets(feature_set_id),
    features JSON NOT NULL,       -- Feature name -> value mapping
    feature_count INTEGER,        -- Number of features extracted
    extraction_time_ms INTEGER,   -- Time taken to extract features
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(config_id, feature_set_id)
);

-- ML Models: stores trained model metadata
CREATE TABLE IF NOT EXISTS ml_models (
    model_id INTEGER PRIMARY KEY DEFAULT nextval('seq_ml_model_id'),
    model_name VARCHAR NOT NULL,
    model_type VARCHAR NOT NULL,  -- e.g., 'random_forest', 'xgboost', 'linear'
    feature_set_id INTEGER REFERENCES feature_sets(feature_set_id),
    target_kpi VARCHAR NOT NULL,  -- Which KPI we're predicting
    hyperparameters JSON,
    metrics JSON,                 -- Training/validation metrics
    feature_importance JSON,      -- Feature importance scores
    model_path VARCHAR,           -- Path to serialized model file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for ML tables
CREATE INDEX IF NOT EXISTS idx_ml_features_config ON ml_features(config_id);
CREATE INDEX IF NOT EXISTS idx_ml_features_set ON ml_features(feature_set_id);
CREATE INDEX IF NOT EXISTS idx_ml_models_target ON ml_models(target_kpi);

-- View for feature matrix with metadata
CREATE OR REPLACE VIEW v_feature_matrix AS
SELECT 
    c.client_name,
    r.run_name,
    bc.config_name,
    bc.config_id,
    bc.battery_capacity_kwh,
    bc.battery_power_kw,
    bc.is_baseline,
    fs.feature_set_name,
    mf.features,
    mf.feature_count
FROM ml_features mf
JOIN battery_configs bc ON mf.config_id = bc.config_id
JOIN runs r ON bc.run_id = r.run_id
JOIN clients c ON r.client_id = c.client_id
JOIN feature_sets fs ON mf.feature_set_id = fs.feature_set_id
ORDER BY c.client_name, r.run_name, bc.battery_capacity_kwh;

