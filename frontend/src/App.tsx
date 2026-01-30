import React, { useState } from 'react';
import backgroundImage from './bg.webp';
import { DataForm } from './components/DataForm';
import { WeeklyHighResChart } from "./components/charts/WeeklyLoadConsumption";
import BenefitWaterfall from "./components/charts/Waterfall";

const App = () => {
    const [chartData, setChartData] = useState(null); // Client-side preview (Line Chart)
    const [waterfallData, setWaterfallData] = useState(null); // Server-side results (Waterfall)
    const [loading, setLoading] = useState(false);

    // -------------------------------------------------------------------
    // 1. Client-Side CSV Logic (Immediate Preview)
    // -------------------------------------------------------------------
    // -------------------------------------------------------------------
    // 1. Client-Side CSV Logic (Aggregation: Average Week)
    // -------------------------------------------------------------------
    const processCSV = (csvText) => {
        try {
            const lines = csvText.split('\n').filter(line => line.trim() !== '');
            const dataRows = lines.slice(1); // Skip header

            // 1. Initialize buckets for 7 days * 96 intervals (15 min) = 672 slots
            // Array index 0 = Mon 00:00, Index 1 = Mon 00:15 ... Index 671 = Sun 23:45
            const buckets = new Array(672).fill(null).map(() => ({ sum: 0, count: 0 }));

            dataRows.forEach((line) => {
                const columns = line.split(',');

                // Parse Value (Column 1 usually, fallback to 0)
                let val = parseFloat(columns[1]);
                if (isNaN(val)) val = parseFloat(columns[0]);
                if (isNaN(val)) return; // Skip bad lines

                // Parse Date (Column 0)
                // We expect ISO format: "2024-01-01 00:00:00+00:00"
                const dateStr = columns[0].replace(/"/g, ''); // Remove quotes if present
                const date = new Date(dateStr);

                if (isNaN(date.getTime())) return;

                // 2. Calculate "Weekly Slot Index"
                // Day: 0 (Sun) - 6 (Sat) in JS. We want 0 (Mon) - 6 (Sun).
                let dayIndex = date.getDay() - 1;
                if (dayIndex === -1) dayIndex = 6; // Fix Sunday (was 0, now 6)

                const hours = date.getHours();
                const minutes = date.getMinutes();

                // Slot within the day (0 to 95)
                const daySlot = (hours * 4) + Math.floor(minutes / 15);

                // Global slot (0 to 671)
                const globalIndex = (dayIndex * 96) + daySlot;

                if (buckets[globalIndex]) {
                    buckets[globalIndex].sum += val;
                    buckets[globalIndex].count += 1;
                }
            });

            // 3. Calculate Averages and Format for Chart
            const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

            const averagedData = buckets.map((bucket, index) => {
                const avgValue = bucket.count > 0 ? bucket.sum / bucket.count : 0;

                // Reconstruct time metadata from the index
                const dayIndex = Math.floor(index / 96);
                const intervalIndex = index % 96;
                const h = Math.floor(intervalIndex / 4);
                const m = (intervalIndex % 4) * 15;
                const timeStr = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;

                return {
                    globalIndex: index,
                    value: avgValue,
                    day: days[dayIndex],
                    time: timeStr
                };
            });

            setChartData(averagedData);

        } catch (error) {
            console.error("Error parsing CSV for preview:", error);
        }
    };


    const handleFileSelect = (file) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const text = e.target?.result;
            processCSV(text);
        };
        reader.readAsText(file);
    };

    // -------------------------------------------------------------------
    // 2. Server-Side Submission Logic
    // -------------------------------------------------------------------
    const handleSubmit = async (formData) => {
        setLoading(true);
        setWaterfallData(null); // Reset previous results

        const payload = new FormData();

        // --- MAP FORM FIELDS TO PYTHON API PARAMETERS ---
        // Left side: Python function argument name
        // Right side: React Form state name
        payload.append('list_battery_usable_max_state', formData.list_battery_usable_max_state);
        payload.append('list_battery_num_annual_cycles', formData.list_battery_num_annual_cycles);
        payload.append('list_battery_proportion_hourly_max_load', formData.list_battery_proportion_hourly_max_load);
        payload.append('pv_peak_power', formData.pv_peak_power);
        payload.append('pv_consumed_percentage', formData.pv_consumed_percentage);

        // Note the name change here to match Python:
        payload.append('working_price_eur_per_kwh', formData.grid_price_work_eur);
        payload.append('power_price_eur_per_kw', formData.grid_price_capacity_eur);

        if (formData.file) {
            payload.append('file', formData.file);
        }

        try {
            const response = await fetch('http://localhost:8000/api/submit-simulation', {
                method: 'POST',
                body: payload,
                // Do NOT set Content-Type header manually; fetch handles multipart boundaries automatically
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Simulation failed');
            }

            const result = await response.json();
            console.log("Server Response:", result);

            // --- UPDATE CHART STATE ---
            // Note: Ensure your Python backend returns these specific keys in the JSON response
            // If the backend returns { results: { ... } }, update this to result.results.peak_shaving...
            if (result.results) {
                setWaterfallData({
                    peak: result.results.peak_shaving_benefit || 0,
                    procurement: result.results.energy_procurement_optimization || 0,
                    trading: result.results.trading_revenue || 0
                });
            } else {
                console.warn("Backend response did not contain results data yet.");
            }

        } catch (error) {
            console.error("Error submitting data:", error);
            alert(`Error: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="pb-20 min-h-screen bg-cover bg-center bg-no-repeat"
             style={{ backgroundImage: `url(${backgroundImage})` }}>

            <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-8 tracking-tight text-center pt-12">
                Trawa Flex
            </h1>

            {/* Input Form */}
            <DataForm
                onSubmit={handleSubmit}
                onFileSelect={handleFileSelect}
            />

            {/* Loading State */}
            {loading && (
                <div className="w-full max-w-2xl mx-auto mt-8 text-center bg-white/90 backdrop-blur-sm p-6 rounded-lg shadow-lg border border-gray-200">
                    <div className="flex items-center justify-center space-x-3">
                        <div className="w-5 h-5 border-t-2 border-b-2 border-green-600 rounded-full animate-spin"></div>
                        <p className="text-gray-700 font-medium">Running Simulation & Optimization...</p>
                    </div>
                </div>
            )}

            {/* Charts Container */}
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12 mt-12">

                {/* 1. Preview Chart (Immediate) */}
                {chartData && (
                    <div className="bg-white p-6 rounded-xl shadow-lg">
                        <h2 className="text-xl font-semibold mb-4 text-gray-800">Load Profile Preview</h2>
                        <WeeklyHighResChart data={chartData} />
                    </div>
                )}

                {/* 2. Results Chart (After Submit) */}
                {waterfallData && (
                    <div className="bg-white p-6 rounded-xl shadow-lg animate-in fade-in slide-in-from-bottom-8 duration-700">
                        <h2 className="text-xl font-semibold mb-4 text-gray-800">Optimization Results</h2>
                        <BenefitWaterfall data={waterfallData} />
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;
