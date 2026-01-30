import React, { useState } from 'react';
import backgroundImage from './bg.webp';
import { DataForm } from './components/DataForm';
import { WeeklyHighResChart } from "./components/charts/WeeklyLoadConsumption";
import BenefitWaterfall from "./components/charts/Waterfall";

const App = () => {
    // State
    const [chartData, setChartData] = useState(null);       // Line Chart (Input Preview)
    const [waterfallData, setWaterfallData] = useState(null); // Waterfall (Output Results)
    const [loading, setLoading] = useState(false);
    const [hasSubmitted, setHasSubmitted] = useState(false); // Controls the "Expansion" of results

    // -------------------------------------------------------------------
    // 1. Client-Side CSV Logic (Calculate Average Weekly Profile)
    // -------------------------------------------------------------------
    const processCSV = (csvText) => {
        try {
            const lines = csvText.split('\n').filter(line => line.trim() !== '');
            const dataRows = lines.slice(1);

            // Initialize 672 buckets (7 days * 96 quarter-hours)
            const buckets = new Array(672).fill(null).map(() => ({ sum: 0, count: 0 }));

            dataRows.forEach((line) => {
                const cols = line.split(',');
                let val = parseFloat(cols[1]);
                if (isNaN(val)) val = parseFloat(cols[0]);
                if (isNaN(val)) return;

                const date = new Date(cols[0].replace(/"/g, ''));
                if (isNaN(date.getTime())) return;

                let dayIndex = date.getDay() - 1;
                if (dayIndex === -1) dayIndex = 6;

                const intervalIndex = (date.getHours() * 4) + Math.floor(date.getMinutes() / 15);
                const globalIndex = (dayIndex * 96) + intervalIndex;

                if (buckets[globalIndex]) {
                    buckets[globalIndex].sum += val;
                    buckets[globalIndex].count += 1;
                }
            });

            const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
            const averagedData = buckets.map((bucket, index) => {
                const dayIdx = Math.floor(index / 96);
                const intervalIdx = index % 96;
                const h = Math.floor(intervalIdx / 4);
                const m = (intervalIdx % 4) * 15;

                return {
                    globalIndex: index,
                    value: bucket.count > 0 ? bucket.sum / bucket.count : 0,
                    day: days[dayIdx],
                    time: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
                };
            });

            setChartData(averagedData);

        } catch (error) {
            console.error("Error parsing CSV:", error);
        }
    };

    const handleFileSelect = (file) => {
        const reader = new FileReader();
        reader.onload = (e) => processCSV(e.target?.result);
        reader.readAsText(file);
    };

    // -------------------------------------------------------------------
    // 2. Server-Side Submission Logic
    // -------------------------------------------------------------------
    const handleSubmit = async (formData) => {
        setLoading(true);
        setWaterfallData(null);
        setHasSubmitted(false);

        const payload = new FormData();
        // Append fields with updated names
        payload.append('list_battery_usable_max_state', formData.list_battery_usable_max_state);
        payload.append('list_battery_num_annual_cycles', formData.list_battery_num_annual_cycles);
        payload.append('list_battery_proportion_hourly_max_load', formData.list_battery_proportion_hourly_max_load);
        payload.append('pv_peak_power', formData.pv_peak_power);
        payload.append('pv_consumed_percentage', formData.pv_consumed_percentage);

        // NEW NAMES MATCHING SERVER.PY UPDATE
        payload.append('static_grid_fees', formData.working_price_eur_per_kwh || 0); // Map old state to new key
        payload.append('grid_fee_max_load_peak', formData.power_price_eur_per_kw || 0); // Map old state to new key

        if (formData.file) payload.append('file', formData.file);

        try {
            const response = await fetch('http://localhost:8000/api/submit-simulation', {
                method: 'POST',
                body: payload,
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Simulation failed');
            }

            const result = await response.json();
            console.log("Server Results:", result);

            // ONLY set data if backend returned results (no more dummy data here)
            if (result.results && Object.keys(result.results).length > 0) {
                setWaterfallData({
                    peak: result.results.peak_shaving_benefit || 0,
                    procurement: result.results.energy_procurement_optimization || 0,
                    trading: result.results.trading_revenue || 0
                });
                setHasSubmitted(true);
            } else {
                console.warn("Backend returned no results.");
                alert("Die Simulation lieferte keine Ergebnisse. Bitte überprüfen Sie Ihre Eingaben.");
            }

        } catch (error) {
            console.error("Error:", error);
            alert("Fehler: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-fixed bg-cover bg-center bg-no-repeat pb-20"
             style={{ backgroundImage: `url(${backgroundImage})` }}>

            <div className="pt-16 text-center">
                <h1 className="text-5xl md:text-6xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-gray-100 to-gray-300 tracking-tight mb-4">
                    trawa baby flex
                </h1>
                <p className="text-xl text-gray-100 font-medium">Energy Storage Optimization Suite</p>
            </div>

            <div className="px-4 animate-in fade-in slide-in-from-bottom-8 duration-700">
                <DataForm
                    onSubmit={handleSubmit}
                    onFileSelect={handleFileSelect}
                    isLoading={loading}
                />
            </div>

            {hasSubmitted && (
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12 mt-16 animate-in fade-in slide-in-from-bottom-12 duration-1000 ease-out fill-mode-forwards">

                    <div className="flex items-center space-x-4 mb-8">
                        <div className="h-px bg-gray-300 flex-1"></div>
                        <span className="text-gray-500 font-semibold uppercase tracking-wider text-sm">Optimization Report</span>
                        <div className="h-px bg-gray-300 flex-1"></div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        <div className="bg-white/95 backdrop-blur rounded-xs p-6 shadow-xl border border-gray-100 transition-transform hover:scale-[1.01] duration-500">
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">Eingangslastprofil</h2>
                            <p className="text-gray-500 text-sm mb-6">Durchschnittliches wöchentliches Verbrauchsverhalten.</p>
                            <WeeklyHighResChart data={chartData} />
                        </div>

                        {waterfallData && (
                            <div className="bg-white/95 backdrop-blur rounded-xs p-6 shadow-xl border border-gray-100 transition-transform hover:scale-[1.01] duration-500 delay-100">
                                <h2 className="text-2xl font-bold text-gray-800 mb-2">Prognostizierter Wert</h2>
                                <p className="text-gray-500 text-sm mb-6">Jährliche Einsparungen nach Einnahmequellen.</p>
                                <BenefitWaterfall data={waterfallData} />
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default App;
