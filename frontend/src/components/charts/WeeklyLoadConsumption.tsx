import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { ChartDataPoint } from '../../types'; // Import shared type

export const WeeklyHighResChart = ({ data }: { data: ChartDataPoint[] | null }) => {
    if (!data || data.length === 0) return null;

    // Visualization Config
    const dayTicks = [48, 144, 240, 336, 432, 528, 624];
    const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const boundaries = [0, 96, 192, 288, 384, 480, 576, 672];

    const formatXAxis = (tickItem: number) => {
        const index = dayTicks.indexOf(tickItem);
        return index >= 0 ? dayLabels[index] : '';
    };

    return (
        <div className="w-full max-w-4xl mx-auto mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* ... keeping your existing JSX ... */}
            <div className="bg-white rounded-md border border-gray-200 p-6 shadow-lg">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h4 className="text-lg font-bold text-gray-900">Lastprofil Analyse</h4>
                        <p className="text-sm text-gray-500">Durchschnittliche Woche (15-min Auflösung)</p>
                    </div>
                </div>

                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                            <defs>
                                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />

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
                                                <div className="font-semibold text-gray-300 mb-1">{d.day} • {d.time} Uhr</div>
                                                <div className="text-emerald-400 text-lg font-bold">{d.value.toFixed(2)} kW</div>
                                            </div>
                                        );
                                    }
                                    return null;
                                }}
                            />
                            <Area
                                type="monotone"
                                dataKey="value"
                                stroke="#10b981"
                                strokeWidth={2}
                                fillOpacity={1}
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
