import React from 'react';
import Chart from 'react-apexcharts';
import {ApexOptions} from 'apexcharts';

const BenefitWaterfall = ({data}: {
    data: { peak: number, procurement: number, trading: number, warning?: string }
}) => {

    const step1_end = data.peak;
    const step2_end = step1_end + data.procurement;
    const step3_end = step2_end + data.trading;

    // 2. Data Series
    const series = [
        {
            name: 'Waterfall',
            data: [
                {
                    x: 'Reduktion d. Netzentgelte',
                    y: [0, step1_end],
                    fillColor: '#34d399',
                },
                {
                    x: 'Optimierter Stromeinkauf',
                    y: [step1_end, step2_end],
                    fillColor: '#3b82f6',
                },
                {
                    x: 'Intraday Trading',
                    y: [step2_end, step3_end],
                    fillColor: '#ED943C', // Orange/Warm Tone
                },
                {
                    x: 'Summe',
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
            toolbar: {show: false},
            zoom: {enabled: false}
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
            formatter: function (value, {seriesIndex, dataPointIndex, w}) {
                const range = w.config.series[seriesIndex].data[dataPointIndex].y;
                const diff = range[1] - range[0];
                return formatLabel(diff);
            }
        },
        yaxis: {
            labels: {
                style: {colors: '#9ca3af', fontSize: '11px'},
                formatter: (val) => formatLabel(val)
            },
        },
        xaxis: {
            categories: [['Reduktion d.', 'Netzentgelte'], ['Optimierter', 'Stromeinkauf'], ['Intraday', 'Trading'], ['Summe']],
            axisBorder: {show: false},
            axisTicks: {show: false},
            labels: {
                style: {colors: '#4b5563', fontSize: '12px', fontWeight: 500},
                offsetY: 5,
                rotate: 0,
            }
        },
        grid: {
            borderColor: '#f3f4f6',
            strokeDashArray: 4,
            yaxis: {lines: {show: true}},
            xaxis: {lines: {show: false}},
            padding: {
                top: 60, // Extra space at the top for labels
                left: 10,
                right: 10
            }
        },
        tooltip: {
            theme: 'dark', // Changed base theme for shadows
            custom: function ({series, seriesIndex, dataPointIndex, w}) {
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
                {data?.warning &&
                    <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                        <div className="flex items-start gap-3">
                            <svg className="h-5 w-5 flex-shrink-0 text-amber-600" viewBox="0 0 20 20"
                                 fill="currentColor"
                                 aria-hidden="true">
                                <path fillRule="evenodd"
                                      d="M8.257 3.099c.765-1.36 2.72-1.36 3.485 0l6.518 11.6c.75 1.334-.213 3-1.742 3H3.48c-1.53 0-2.493-1.666-1.742-3l6.518-11.6zM11 14a1 1 0 10-2 0 1 1 0 002 0zm-1-8a1 1 0 00-1 1v4a1 1 0 102 0V7a1 1 0 00-1-1z"
                                      clipRule="evenodd"/>
                            </svg>
                            <div className="text-sm">
                                <p className="font-medium text-amber-900">Hinweis</p>
                                <p className="mt-1 text-amber-800">
                                    {data?.warning}
                                </p>
                            </div>
                        </div>
                    </div>}

            </div>
        </div>
    );
};

export default BenefitWaterfall;
