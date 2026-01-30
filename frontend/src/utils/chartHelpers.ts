import { ChartDataPoint, BackendTimeSeriesRow } from '../types';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// --- Internal Helper: Add value to the correct 15-min bucket ---
const fillBucket = (buckets: any[], date: Date, val: number) => {
    let dayIndex = date.getDay() - 1; // 0=Mon, 6=Sun
    if (dayIndex === -1) dayIndex = 6;

    // Calculate index (0 to 672 for a full week of 15-min intervals)
    const intervalIndex = (date.getHours() * 4) + Math.floor(date.getMinutes() / 15);
    const globalIndex = (dayIndex * 96) + intervalIndex;

    if (buckets[globalIndex]) {
        buckets[globalIndex].sum += val;
        buckets[globalIndex].count += 1;
    }
};

// --- Internal Helper: Average the buckets ---
const computeAverages = (buckets: any[]): ChartDataPoint[] => {
    return buckets.map((bucket, index) => {
        const dayIdx = Math.floor(index / 96);
        const intervalIdx = index % 96;
        const h = Math.floor(intervalIdx / 4);
        const m = (intervalIdx % 4) * 15;

        return {
            globalIndex: index,
            value: bucket.count > 0 ? bucket.sum / bucket.count : 0,
            day: DAYS[dayIdx],
            time: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
        };
    });
};

// --- Exported: Parse Raw CSV Text (Input Preview) ---
export const parseCSVData = (csvText: string): ChartDataPoint[] => {
    const buckets = new Array(672).fill(null).map(() => ({ sum: 0, count: 0 }));
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

        fillBucket(buckets, date, val);
    });

    return computeAverages(buckets);
};

// --- Exported: Parse Backend JSON (Simulation Result) ---
export const parseBackendData = (dataArray: BackendTimeSeriesRow[]): ChartDataPoint[] => {
    const buckets = new Array(672).fill(null).map(() => ({ sum: 0, count: 0 }));

    dataArray.forEach((row) => {
        // Prioritize calculated consumption, fall back to grid load
        const val = row.consumption_kwh ?? row.grid_load_kwh ?? 0;
        const date = new Date(row.timestamp_utc);
        fillBucket(buckets, date, val);
    });

    return computeAverages(buckets);
};
