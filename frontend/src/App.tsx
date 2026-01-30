import React, { useState } from 'react';
import backgroundImage from './bg.webp';
import { DataForm } from './components/DataForm';
import { WeeklyHighResChart } from "./components/charts/WeeklyLoadConsumption";
import BenefitWaterfall from "./components/charts/Waterfall";
import { parseCSVData, parseBackendData } from './utils/chartHelpers';
import { submitSimulation, fetchSimulationTimeseries } from './api/simulationApi';
import { ChartDataPoint, SimulationWaterfallResults } from './types';

const App = () => {
    const [chartData, setChartData] = useState<ChartDataPoint[] | null>(null);
    const [waterfallData, setWaterfallData] = useState<SimulationWaterfallResults | null>(null);
    const [loading, setLoading] = useState(false);
    const [hasSubmitted, setHasSubmitted] = useState(false);

    // 1. Handle File Upload (Preview Input)
    const handleFileSelect = (file: File) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            if (e.target?.result) {
                const processed = parseCSVData(e.target.result as string);
                setChartData(processed);
            }
        };
        reader.readAsText(file);
    };

    // 2. Handle Simulation Submission
    const handleSubmit = async (formData: any) => {
        setLoading(true);
        setWaterfallData(null);
        setHasSubmitted(false);

        try {
            // A. Trigger Simulation
            const result = await submitSimulation(formData);
            console.log("Server Results:", result);

            if (result.results && Object.keys(result.results).length > 0) {
                // B. Update Financials
                setWaterfallData({
                    peak: result.results.peak_shaving_benefit || 0,
                    procurement: result.results.energy_procurement_optimization || 0,
                    trading: result.results.trading_revenue || 0
                });
                setHasSubmitted(true);

                // C. Fetch & Update Chart with Simulated Data
                await loadSimulationChart();
            } else {
                alert("Die Simulation lieferte keine Ergebnisse.");
            }
        } catch (error: any) {
            console.error("Error:", error);
            alert("Fehler: " + error.message);
        } finally {
            setLoading(false);
        }
    };

    const loadSimulationChart = async () => {
        try {
            console.log("Fetching new timeseries data...");
            const result = await fetchSimulationTimeseries();
            if (result.data && result.data.length > 0) {
                const processed = parseBackendData(result.data);
                setChartData(processed);
                console.log("Chart updated with simulation data");
            }
        } catch (e) {
            console.error("Error fetching timeseries:", e);
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
                        {/* Chart */}
                        <div className="bg-white/95 backdrop-blur rounded-xs p-6 shadow-xl border border-gray-100 transition-transform hover:scale-[1.01] duration-500">
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">Eingangslastprofil</h2>
                            <p className="text-gray-500 text-sm mb-6">
                                {waterfallData ? "Simuliertes Profil (Inkl. PV)" : "Durchschnittliches wöchentliches Verbrauchsverhalten (Input)"}
                            </p>
                            <WeeklyHighResChart data={chartData} />
                        </div>

                        {/* Waterfall */}
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
};

export default App;
