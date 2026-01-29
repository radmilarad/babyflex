import React from 'react';
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

const data = [
    { time: '09:00', value: 40 },
    { time: '10:00', value: 60 },
    { time: '11:00', value: 45 },
    { time: '12:00', value: 90 }, // The spike
    { time: '13:00', value: 55 },
    { time: '14:00', value: 30 },
    { time: '15:00', value: 65 },
    { time: '16:00', value: 50 },
    { time: '17:00', value: 40 },
    { time: '18:00', value: 80 },
    { time: '19:00', value: 45 },
    { time: '20:00', value: 35 },
];

const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-gray-800 text-white text-xs py-1 px-2 rounded shadow-lg">
                <p>{`${payload[0].value} MWh`}</p>
            </div>
        );
    }
    return null;
};

export const ConsumptionChart = () => {
    return (
        <div className="bg-white p-6 rounded-sm shadow-sm border border-gray-100">
            <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900">Verbrauch</h3>
                <p className="text-sm text-gray-500">Gesamt: 3 MWh</p>
            </div>

            <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data} barSize={12}>
                        <CartesianGrid vertical={false} stroke="#E5E7EB" strokeDasharray="3 3" />
                        <XAxis
                            dataKey="time"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fontSize: 10, fill: '#9CA3AF' }}
                            dy={10}
                        />
                        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                        <Bar
                            dataKey="value"
                            fill="#10B981" // Emerald-500
                            radius={[4, 4, 0, 0]} // Rounded top corners
                        />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
