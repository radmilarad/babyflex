const API_BASE = 'http://localhost:8000/api';

export const submitSimulation = async (formData: any) => {
    const payload = new FormData();
    payload.append('list_battery_usable_max_state', formData.list_battery_usable_max_state);
    payload.append('list_battery_num_annual_cycles', formData.list_battery_num_annual_cycles);
    payload.append('list_battery_proportion_hourly_max_load', formData.list_battery_proportion_hourly_max_load);
    payload.append('pv_peak_power', formData.pv_peak_power);
    payload.append('pv_consumed_percentage', formData.pv_consumed_percentage);

    // Map new backend names
    payload.append('static_grid_fees', formData.working_price_eur_per_kwh || 0);
    payload.append('grid_fee_max_load_peak', formData.power_price_eur_per_kw || 0);

    if (formData.file) payload.append('file', formData.file);

    const response = await fetch(`${API_BASE}/submit-simulation`, {
        method: 'POST',
        body: payload,
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Simulation failed');
    }
    return await response.json();
};

export const fetchSimulationTimeseries = async () => {
    const response = await fetch(`${API_BASE}/simulation-timeseries`);
    if (!response.ok) throw new Error("Failed to fetch timeseries");
    return await response.json();
};
