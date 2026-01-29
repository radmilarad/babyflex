import React from 'react';
import Chart from 'react-apexcharts';
import { ApexOptions } from 'apexcharts';

const raw = {
    peak: 204038,
    procurement: 284739,
    trading: 294384
};

const BenefitWaterfall = ({ data }) => {

    const step1_end = data.peak;
    const step2_end = step1_end + data.procurement;
    const step3_end = step2_end + data.trading;

    // 2. Data Series
    const series = [
        {
            name: 'Waterfall',
            data: [
                {
                    x: 'Peak Shaving',
                    y: [0, step1_end],
                    fillColor: '#34d399',
                },
                {
                    x: 'Procurement',
                    y: [step1_end, step2_end],
                    fillColor: '#3b82f6',
                },
                {
                    x: 'Trading Rev.',
                    y: [step2_end, step3_end],
                    fillColor: '#ED943C', // Orange/Warm Tone
                },
                {
                    x: 'Total Benefit',
                    y: [0, step3_end],
                    fillColor: '#1f2937',
                }
            ]
        }
    ];

    // 3. Formatters
    const formatCurrency = (val: number) => {
        return new Intl.NumberFormat('de-DE', {
            style: 'currency',
            currency: 'EUR',
            maximumFractionDigits: 0
        }).format(val);
    };

    const formatLabel = (val: number) => {
        if (val >= 1000000) return (val / 1000000).toFixed(1) + 'M€';
        if (val >= 1000) return (val / 1000).toFixed(0) + 'k€';
        return val.toFixed(0) + '€';
    };

    // 4. Configuration
    const options: ApexOptions = {
        chart: {
            type: 'rangeBar',
            fontFamily: 'Inter, sans-serif',
            toolbar: { show: false },
            zoom: { enabled: false }
        },
        plotOptions: {
            bar: {
                horizontal: false,
                columnWidth: '70%',
                borderRadius: 2,
                dataLabels: {
                    position: 'top',
                }
            }
        },
        dataLabels: {
            enabled: true,
            offsetY: -40, // Increased margin between bar and label
            style: {
                fontSize: '13px',
                fontWeight: 700,
                colors: ['#374151']
            },
            formatter: function (value, { seriesIndex, dataPointIndex, w }) {
                const range = w.config.series[seriesIndex].data[dataPointIndex].y;
                const diff = range[1] - range[0];
                return formatLabel(diff);
            }
        },
        yaxis: {
            labels: {
                style: { colors: '#9ca3af', fontSize: '11px' },
                formatter: (val) => formatLabel(val)
            },
        },
        xaxis: {
            categories: ['Peak Shaving', 'Procurement', 'Trading', 'Total'],
            axisBorder: { show: false },
            axisTicks: { show: false },
            labels: {
                style: { colors: '#4b5563', fontSize: '12px', fontWeight: 500 },
                offsetY: 5
            }
        },
        grid: {
            borderColor: '#f3f4f6',
            strokeDashArray: 4,
            yaxis: { lines: { show: true } },
            xaxis: { lines: { show: false } },
            padding: {
                top: 60, // Extra space at the top for labels
                left: 10,
                right: 10
            }
        },
        tooltip: {
            theme: 'dark', // Changed base theme for shadows
            custom: function({ series, seriesIndex, dataPointIndex, w }) {
                const data = w.config.series[seriesIndex].data[dataPointIndex];
                const range = data.y;
                const value = range[1] - range[0];
                const label = data.x;

                // Dark Tooltip Style matching your screenshot
                return `
          <div class="bg-gray-900 text-white text-xs rounded-lg py-3 px-4 shadow-xl border border-gray-800">
            <div class="font-semibold text-gray-300 mb-1">${label}</div>
            <div class="text-emerald-400 text-lg font-bold">${formatCurrency(value)}</div>
          </div>
        `;
            }
        }
    };

    return (
        <div className="w-full max-w-4xl mt-6 mx-auto bg-white p-8 rounded-md shadow-sm border border-gray-100">
            <div className="mb-6">
                <h3 className="text-xl font-bold text-gray-900">Einsparungen & Erlöse</h3>
                <p className="text-sm text-gray-500 mt-1">Zusammensetzung Ihres Gesamtergebnisses</p>
            </div>

            <div className="relative">
                <Chart
                    options={options}
                    series={series}
                    type="rangeBar"
                    height={350}
                />
            </div>
        </div>
    );
};

export default BenefitWaterfall;
