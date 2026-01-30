import { ChartDataPoint, BackendTimeSeriesRow } from '../types';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// --- Internal Helper: Bucket Definition ---
interface Bucket {
    sum: number;    // Sum of Consumption (Net Load)
    pvSum: number;  // Sum of PV Generation
    count: number;  // Number of data points in this bucket
}

// --- Internal Helper: Add value to the correct 15-min bucket ---
const fillBucket = (buckets: Bucket[], date: Date, val: number, pvVal: number) => {
    let dayIndex = date.getDay() - 1; // 0=Mon, 6=Sun
    if (dayIndex === -1) dayIndex = 6;

    // Calculate index (0 to 672 for a full week of 15-min intervals)
    const intervalIndex = (date.getHours() * 4) + Math.floor(date.getMinutes() / 15);
    const globalIndex = (dayIndex * 96) + intervalIndex;

    if (buckets[globalIndex]) {
        buckets[globalIndex].sum += val;
        buckets[globalIndex].pvSum += pvVal;
        buckets[globalIndex].count += 1;
    }
};

// --- Internal Helper: Average the buckets into ChartDataPoints ---
const computeAverages = (buckets: Bucket[]): ChartDataPoint[] => {
    return buckets.map((bucket, index) => {
        const dayIdx = Math.floor(index / 96);
        const intervalIdx = index % 96;
        const h = Math.floor(intervalIdx / 4);
        const m = (intervalIdx % 4) * 15;

        return {
            globalIndex: index,
            // Average Net Consumption
            value: bucket.count > 0 ? bucket.sum / bucket.count : 0,
            // Average PV Generation
            pv: bucket.count > 0 ? bucket.pvSum / bucket.count : 0,

            day: DAYS[dayIdx],
            time: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
        };
    });
};

// --- Exported: Parse Raw CSV Text (Input Preview) ---
export const parseCSVData = (csvText: string): ChartDataPoint[] => {
    // Initialize 672 buckets
    const buckets: Bucket[] = new Array(672).fill(null).map(() => ({ sum: 0, pvSum: 0, count: 0 }));

    const lines = csvText.split('\n').filter(line => line.trim() !== '');
    // Skip header
    const dataRows = lines.slice(1);

    dataRows.forEach((line) => {
        const cols = line.split(',');
        // Try col 1 (value), fallback to col 0
        let val = parseFloat(cols[1]);
        if (isNaN(val)) val = parseFloat(cols[0]);
        if (isNaN(val)) return;

        // Clean quotes from date string
        const date = new Date(cols[0].replace(/"/g, ''));
        if (isNaN(date.getTime())) return;

        // For raw input CSV, we assume 0 PV
        fillBucket(buckets, date, val, 0);
    });

    return computeAverages(buckets);
};

// --- Exported: Parse Backend JSON (Simulation Result) ---
export const parseBackendData = (dataArray: BackendTimeSeriesRow[]): ChartDataPoint[] => {
    // Initialize 672 buckets
    const buckets: Bucket[] = new Array(672).fill(null).map(() => ({ sum: 0, pvSum: 0, count: 0 }));

    dataArray.forEach((row) => {
        // 1. Consumption (Net Load)
        // Prefer 'consumption_kwh' (calculated), fallback to 'grid_load_kwh' (original)
        const val = row.consumption_kwh ?? row.grid_load_kwh ?? 0;

        // 2. PV Generation
        // Explicitly look for 'pv_load_kwh'
        const pvVal = row.pv_load_kwh ?? 0;

        const date = new Date(row.timestamp_utc);

        fillBucket(buckets, date, val, pvVal);
    });

    return computeAverages(buckets);
};
