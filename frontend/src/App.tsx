import React, { useState } from 'react';
import backgroundImage from './bg.webp';
import { DataForm } from './components/DataForm';
import { WeeklyHighResChart } from "./components/charts/WeeklyLoadConsumption";
import BenefitWaterfall from "./components/charts/Waterfall";

const App = () => {
    const [chartData, setChartData] = useState(null); // For the line chart (Client-side)
    const [waterfallData, setWaterfallData] = useState(null); // For the waterfall (Server-side)
    const [loading, setLoading] = useState(false);

    // --- 1. Client-Side Chart Logic (Keep this for instant preview) ---
    const processCSV = (csvText) => {
        // ... (Your existing CSV processing logic for the line chart) ...
        // I'm hiding it here for brevity, but keep your existing code!
        const lines = csvText.split('\n');
        const rows = lines.slice(1).filter(line => line.trim() !== '');
        // ... stats logic ...
        // setChartData(flatData);
    };

    const handleFileSelect = (file) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const text = e.target?.result;
            processCSV(text); // Updates the Weekly Chart immediately
        };
        reader.readAsText(file);
    };

    // --- 2. Server-Side Analysis Logic (New!) ---
    const handleSubmit = async (formData) => {
        setLoading(true);
        setWaterfallData(null); // Reset old results

        // Prepare data for FastAPI (multipart/form-data)
        const payload = new FormData();
        payload.append('pv_peak_power', formData.pv_peak_power);
        payload.append('pv_consumed_percentage', formData.pv_consumed_percentage);
        payload.append('list_battery_usable_max_state', formData.list_battery_usable_max_state);
        payload.append('list_battery_num_annual_cycles', formData.list_battery_num_annual_cycles);
        payload.append('list_battery_proportion_hourly_max_load', formData.list_battery_proportion_hourly_max_load);
        payload.append('grid_price_work_eur', formData.grid_price_work_eur);
        payload.append('grid_price_capacity_eur', formData.grid_price_capacity_eur);

        console.log(payload)

        if (formData.file) {
            payload.append('file', formData.file);
        }

        try {
            // Adjust URL if your server runs on a different port (e.g. 8000)
            const response = await fetch('http://localhost:8000/api/analyze', {
                method: 'POST',
                body: payload,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || 'Analysis failed');
            }

            const result = await response.json();

            // Map API response to Waterfall component props
            setWaterfallData({
                peak: result.peak_shaving_benefit,
                procurement: result.energy_procurement_optimization,
                trading: result.trading_revenue
            });

        } catch (error) {
            console.error("Error submitting data:", error);
            alert("Fehler bei der Analyse: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="pb-20" style={{
            backgroundImage: `url(${backgroundImage})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            minHeight: "100vh",
        }}>
            <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-8 tracking-tight text-center pt-12">
                Trawa flex
            </h1>

            {/* Pass handleSubmit to DataForm */}
            <DataForm
                onSubmit={handleSubmit}
                onFileSelect={handleFileSelect}
            />

            {/* Loading Indicator */}
            {loading && (
                <div className="w-full max-w-2xl mx-auto mt-8 text-center bg-white p-4 rounded-md shadow-sm">
                    <p className="text-gray-600 animate-pulse">Analysiere Daten...</p>
                </div>
            )}

            {/* 1. Client-Side Preview Chart */}
            <WeeklyHighResChart data={chartData} />

            {/* 2. Server-Side Waterfall Chart (Only shows after submit) */}
            {waterfallData && (
                <div className="mt-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <BenefitWaterfall data={waterfallData} />
                </div>
            )}
        </div>
    );
}

export default App;
