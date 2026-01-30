import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { ChartDataPoint } from '../../types';

export const WeeklyHighResChart = ({ data }: { data: ChartDataPoint[] | null }) => {
    if (!data || data.length === 0) return null;

    // Visualization Config
    const dayTicks = [48, 144, 240, 336, 432, 528, 624]; // Center of each day (0-96)
    const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const boundaries = [0, 96, 192, 288, 384, 480, 576, 672]; // Vertical grid lines

    const formatXAxis = (tickItem: number) => {
        const index = dayTicks.indexOf(tickItem);
        return index >= 0 ? dayLabels[index] : '';
    };

    return (
        <div className="w-full max-w-4xl mx-auto mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-white rounded-md border border-gray-200 p-6 shadow-lg">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h4 className="text-lg font-bold text-gray-900">Lastprofil Analyse</h4>
                        <p className="text-sm text-gray-500">Durchschnittliche Woche (15-min Auflösung)</p>
                    </div>

                    {/* Optional: Legend/Key */}
                    <div className="flex items-center space-x-4 text-xs font-medium">
                        <div className="flex items-center">
                            <span className="w-3 h-3 rounded-full bg-emerald-500 mr-2"></span>
                            <span className="text-gray-600">Netzbezug</span>
                        </div>
                        <div className="flex items-center">
                            <span className="w-3 h-3 rounded-full bg-orange-500 mr-2"></span>
                            <span className="text-gray-600">PV Erzeugung</span>
                        </div>
                    </div>
                </div>

                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <defs>
                                {/* Green Gradient (Net Load) */}
                                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                                </linearGradient>

                                {/* Orange Gradient (PV) */}
                                <linearGradient id="colorPv" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.1}/>
                                    <stop offset="95%" stopColor="#f97316" stopOpacity={0}/>
                                </linearGradient>
                            </defs>

                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />

                            {/* Vertical Separators for Days */}
                            {boundaries.map((x) => (
                                <ReferenceLine key={x} x={x} stroke="#e5e7eb" strokeDasharray="3 3" />
                            ))}

                            <XAxis
                                dataKey="globalIndex"
                                ticks={dayTicks}
                                tickFormatter={formatXAxis}
                                tick={{ fontSize: 13, fontWeight: 600, fill: '#6b7280' }}
                                axisLine={false}
                                tickLine={false}
                                dy={10}
                            />
                            <YAxis
                                tick={{ fontSize: 12, fill: '#9ca3af' }}
                                axisLine={false}
                                tickLine={false}
                                width={40}
                            />

                            <Tooltip
                                content={({ active, payload }) => {
                                    if (active && payload && payload.length) {
                                        const d = payload[0].payload as ChartDataPoint;
                                        return (
                                            <div className="bg-gray-900 text-white text-xs rounded-lg py-2 px-3 shadow-xl border border-gray-800">
                                                <div className="font-semibold text-gray-300 mb-2 border-b border-gray-700 pb-1">
                                                    {d.day} • {d.time} Uhr
                                                </div>
                                                <div className="flex justify-between space-x-4 mb-1">
                                                    <span className="text-gray-400">Netz:</span>
                                                    <span className="text-emerald-400 font-bold">{d.value.toFixed(2)} kW</span>
                                                </div>
                                                {d.pv > 0 && (
                                                    <div className="flex justify-between space-x-4">
                                                        <span className="text-gray-400">PV:</span>
                                                        <span className="text-orange-400 font-bold">{d.pv.toFixed(2)} kW</span>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    }
                                    return null;
                                }}
                            />

                            {/* PV Area (Orange) - Render first so it's "behind" if needed, or manage via opacity */}
                            <Area
                                type="monotone"
                                dataKey="pv"
                                stroke="#f97316"
                                strokeWidth={2}
                                fillOpacity={1}
                                fill="url(#colorPv)"
                                activeDot={{ r: 4, strokeWidth: 0, fill: '#ea580c' }}
                            />

                            {/* Net Load Area (Green) */}
                            <Area
                                type="monotone"
                                dataKey="value"
                                stroke="#10b981"
                                strokeWidth={2}
                                fillOpacity={0.6} // Slight opacity to see PV if they overlap heavily
                                fill="url(#colorValue)"
                                activeDot={{ r: 6, strokeWidth: 0, fill: '#059669' }}
                            />

                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};
