import React from 'react';
import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

const data = [
    { time: '00:00', price: 20 },
    { time: '02:00', price: 25 },
    { time: '04:00', price: 20 },
    { time: '06:00', price: 80 }, // Morning spike
    { time: '08:00', price: 50 },
    { time: '10:00', price: 30 },
    { time: '12:00', price: 60 },
    { time: '14:00', price: 25 },
    { time: '16:00', price: 70 },
    { time: '18:00', price: 30 },
    { time: '20:00', price: 45 },
    { time: '22:00', price: 40 },
];

export const PriceChart = () => {
    return (
        <div className="bg-white p-6 rounded-s shadow-sm border border-gray-100 mt-6">
            <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900">Preis Strombörse</h3>
                <p className="text-sm text-gray-500">Gesamt: 453€</p>
            </div>

            <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid vertical={true} horizontal={true} stroke="#F3F4F6" />
                        <XAxis hide />
                        <Tooltip />
                        <Area
                            type="step" // This creates the "squared" look
                            dataKey="price"
                            stroke="#3B82F6" // Blue-500
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorPrice)"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
