export interface ChartDataPoint {
    day: string;
    time: string;
    value: number;
    globalIndex: number;
}

export interface BackendTimeSeriesRow {
    timestamp_utc: string;
    consumption_kwh?: number; // Calculated (Load + PV)
    grid_load_kwh?: number;   // Original Load
    [key: string]: any;
}

export interface SimulationWaterfallResults {
    peak: number;
    procurement: number;
    trading: number;
}
