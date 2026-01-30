import React, { useState, ChangeEvent, FormEvent } from 'react';
import AddressInput from "./AddressInput";

// 1. Update Interface to include Grid/Address Data
interface FormData {
    pvPower: number | '';
    pvConsumed: number | ''; // User enters 80 (%), we send 0.8
    batteryCapacity: number | '';
    batteryPower: number | '';
    batteryCycles: number | '';
    file: File | null;
    gridData: any | null;
}

interface DataFormProps {
    onSubmit: (data: any) => void;
    onFileSelect?: (file: File) => void;
    isLoading?: boolean; // Added isLoading prop
}

export const DataForm: React.FC<DataFormProps> = ({ onSubmit, onFileSelect, isLoading = false }) => {
    const [formData, setFormData] = useState<FormData>({
        pvPower: '',
        pvConsumed: '',
        batteryCapacity: '',
        batteryPower: '',
        batteryCycles: '',
        file: null,
        gridData: null,
    });

    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
        const { name, value, type } = e.target;
        setFormData({
            ...formData,
            [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value,
        });
    };

    const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] || null;
        setFormData({ ...formData, file });

        if (file && onFileSelect) {
            onFileSelect(file);
        }
    };

    const handleGridFee = (data: any) => {
        console.log("📍 Captured Grid Data:", data);
        setFormData(prev => ({ ...prev, gridData: data }));
    };

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();

        // 🧮 1. CALCULATE DERIVED VALUES
        const batteryPower = Number(formData.batteryPower) || 0;
        const batteryCapacity = Number(formData.batteryCapacity) || 0;

        // Calculate C-Rate (Power / Capacity) - Avoid division by zero
        const proportionHourlyMaxLoad = batteryCapacity > 0
            ? Number((batteryPower / batteryCapacity).toFixed(3))
            : 0;

        // Convert Percentage (80) to Decimal (0.8)
        const pvConsumedDecimal = Number(formData.pvConsumed) / 100;

        // Convert Prices: Cents -> Euros (if grid data exists)
        // Assuming gridData.arbeitspreis is in cents/kWh -> convert to EUR/kWh
        // Add default if no grid data selected for testing
        const gridPriceWorkEur = formData.gridData?.arbeitspreis
            ? formData.gridData.arbeitspreis / 100 + 0.03547
            : 0.041; // Default fallback

        // 📦 2. PREPARE FINAL PAYLOAD
        const submissionData = {
            // Renamed fields as requested
            list_battery_usable_max_state: batteryCapacity,
            list_battery_num_annual_cycles: Number(formData.batteryCycles),
            list_battery_proportion_hourly_max_load: proportionHourlyMaxLoad,
            pv_peak_power: Number(formData.pvPower),
            pv_consumed_percentage: pvConsumedDecimal,

            // Grid Data (converted to Euros)
            working_price_eur_per_kwh: gridPriceWorkEur,
            // power_price_eur_per_kw expects EUR, API usually returns EUR
            power_price_eur_per_kw: formData.gridData?.leistungspreis || 138.71,

            // File object passed separately by parent, but good to have here
            file: formData.file
        };

        if (onSubmit) {
            onSubmit(submissionData);
        }
    };

    // Styling constants
    const labelStyle = "block text-sm font-medium text-gray-700 mb-1.5";
    const inputStyle = "block w-full rounded-md border border-gray-200 bg-white pl-14 pr-4 py-2.5 text-gray-900 focus:border-emerald-500 focus:ring-emerald-500 outline-none transition-all shadow-sm sm:text-sm";
    const unitStyle = "absolute left-3 top-2.5 text-gray-500 text-sm font-medium pointer-events-none";

    return (
        <div className="w-full flex flex-col items-center justify-center py-12 px-4">
            <form
                onSubmit={handleSubmit}
                className="w-full max-w-2xl bg-white rounded-md p-6 sm:p-8 shadow-2xl"
            >
                {/* Section: Location */}
                <div className="mb-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 border-b pb-2 border-gray-200">
                        Standort
                    </h3>
                    <div>
                        <label className={labelStyle}>Adresse</label>
                        <AddressInput onGridFeeFetched={handleGridFee} />
                        {/* Hidden validation hack to ensure grid data is present if needed */}
                        <input
                            type="hidden"
                            // required // Uncomment if address is mandatory
                            checked={!!formData.gridData}
                            onChange={() => {}}
                        />
                    </div>
                </div>

                {/* Section: PV */}
                <div className="mb-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 border-b pb-2 border-gray-200">
                        Photovoltaik
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="pvPower" className={labelStyle}>PV Leistung</label>
                            <div className="relative group">
                                <span className={unitStyle}>kWp</span>
                                <input
                                    type="number"
                                    name="pvPower"
                                    id="pvPower"
                                    value={formData.pvPower}
                                    onChange={handleChange}
                                    className={inputStyle}
                                    placeholder="0.00"
                                    min="0"
                                    step="0.1"
                                    required
                                />
                            </div>
                        </div>

                        <div>
                            <label htmlFor="pvConsumed" className={labelStyle}>PV Eigenverbrauch</label>
                            <div className="relative group">
                                <span className={unitStyle}>%</span>
                                <input
                                    type="number"
                                    name="pvConsumed"
                                    id="pvConsumed"
                                    value={formData.pvConsumed}
                                    onChange={handleChange}
                                    className={inputStyle}
                                    placeholder="80"
                                    min="0"
                                    max="100"
                                    step="1"
                                    required
                                />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Section: Battery Storage */}
                <div className="mb-6">
                    <div className="bg-emerald-50/50 rounded-md border border-emerald-100 p-5">
                        <div className="flex items-center gap-3 mb-5">
                            <div className="p-2 bg-white rounded-md shadow-sm text-emerald-600 border border-emerald-100">
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
                                    <path fillRule="evenodd" d="M3.75 6.75a3 3 0 00-3 3v6a3 3 0 003 3h15a3 3 0 003-3v-.037c.856-.174 1.5-.93 1.5-1.838v-2.25c0-.907-.644-1.664-1.5-1.837V9.75a3 3 0 00-3-3h-15zm15 1.5a1.5 1.5 0 011.5 1.5v6a1.5 1.5 0 01-1.5 1.5h-15a1.5 1.5 0 01-1.5-1.5v-6a1.5 1.5 0 011.5-1.5h15zM11.25 9.75a.75.75 0 00-1.5 0v2.25H7.5a.75.75 0 000 1.5h2.25v2.25a.75.75 0 001.5 0v-2.25h2.25a.75.75 0 000-1.5h-2.25V9.75z" clipRule="evenodd" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-gray-900">Batteriespeicher</h3>
                                <p className="text-xs text-gray-500">Technische Parameter</p>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label htmlFor="batteryCapacity" className={labelStyle}>Max. nutzbare Kapazität</label>
                                <div className="relative">
                                    <span className={unitStyle}>kWh</span>
                                    <input
                                        type="number"
                                        name="batteryCapacity"
                                        id="batteryCapacity"
                                        value={formData.batteryCapacity}
                                        onChange={handleChange}
                                        className={`${inputStyle} border-emerald-100 focus:border-emerald-500`}
                                        placeholder="0.00"
                                        min="0"
                                        required
                                    />
                                </div>
                            </div>
                            <div>
                                <label htmlFor="batteryPower" className={labelStyle}>Max. Leistung</label>
                                <div className="relative">
                                    <span className={unitStyle}>kW</span>
                                    <input
                                        type="number"
                                        name="batteryPower"
                                        id="batteryPower"
                                        value={formData.batteryPower}
                                        onChange={handleChange}
                                        className={`${inputStyle} border-emerald-100 focus:border-emerald-500`}
                                        placeholder="0.00"
                                        min="0"
                                        required
                                    />
                                </div>
                            </div>
                            <div className="md:col-span-2">
                                <label htmlFor="batteryCycles" className={labelStyle}>Max. jährliche Zyklen</label>
                                <div className="relative">
                                    <span className={unitStyle}>Cycles</span>
                                    <input
                                        type="number"
                                        name="batteryCycles"
                                        id="batteryCycles"
                                        value={formData.batteryCycles}
                                        onChange={handleChange}
                                        className={`${inputStyle} border-emerald-100 focus:border-emerald-500`}
                                        style={{ paddingLeft: '4.5rem' }}
                                        placeholder="250"
                                        min="0"
                                        required
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Section: Upload */}
                <div className="mb-8">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 border-b pb-2 border-gray-200">
                        Daten-Upload
                    </h3>
                    <label className={labelStyle}>Lastgang hochladen (CSV)</label>

                    <div className="mt-2 flex justify-center rounded-md border border-dashed border-gray-300 px-6 py-8 hover:bg-gray-50 transition-colors relative bg-gray-50/50">
                        <input
                            type="file"
                            name="file"
                            id="file"
                            accept=".csv"
                            onChange={handleFileChange}
                            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                            required={!formData.file}
                        />

                        <div className="text-center">
                            {!formData.file ? (
                                <>
                                    <svg className="mx-auto h-12 w-12 text-gray-300" viewBox="0 0 24 24" fill="currentColor">
                                        <path fillRule="evenodd" clipRule="evenodd" d="M1.5 6a2.25 2.25 0 012.25-2.25h16.5A2.25 2.25 0 0122.5 6v12a2.25 2.25 0 01-2.25 2.25H3.75A2.25 2.25 0 011.5 18V6zM3 16.06V18c0 .414.336.75.75.75h16.5A.75.75 0 0021 18v-1.94l-2.69-2.689a1.5 1.5 0 00-2.12 0l-.88.879.97.97a.75.75 0 11-1.06 1.06l-5.16-5.159a1.5 1.5 0 00-2.12 0L3 16.061zm10.125-7.81a1.125 1.125 0 112.25 0 1.125 1.125 0 01-2.25 0z" />
                                    </svg>
                                    <div className="mt-4 flex text-sm leading-6 text-gray-600 justify-center">
                                        <span className="relative cursor-pointer rounded-md bg-transparent font-semibold text-emerald-600 focus-within:outline-none hover:text-emerald-500">
                                            Datei auswählen
                                        </span>
                                        <p className="pl-1">oder hierher ziehen</p>
                                    </div>
                                    <p className="text-xs leading-5 text-gray-600">CSV bis zu 10MB</p>
                                </>
                            ) : (
                                <div className="flex flex-col items-center">
                                    <div className="p-3 bg-emerald-100 rounded-full text-emerald-600 mb-3">
                                        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                    </div>
                                    <p className="text-sm font-semibold text-gray-900">
                                        {formData.file.name}
                                    </p>
                                    <p className="text-xs text-emerald-600 mt-1">Klicken zum Ändern</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Submit Button */}
                <button
                    type="submit"
                    disabled={isLoading}
                    className={`w-full rounded-md text-white text-lg py-4 font-medium transition-all shadow-lg hover:shadow-xl transform active:scale-[0.99] flex items-center justify-center gap-2
                    ${isLoading ? 'bg-gray-400 cursor-not-allowed' : 'bg-gray-900 hover:bg-emerald-600'}`}
                >
                    {isLoading ? (
                        <>
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                            <span>Analysiere Daten...</span>
                        </>
                    ) : (
                        "Analyse starten"
                    )}
                </button>
            </form>
        </div>
    );
};
