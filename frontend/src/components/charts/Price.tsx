import React, {PureComponent} from 'react';
import {LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer} from 'recharts';

const data = [
    {'day': 'Mon', 'value': 78.53},
    {'day': 'Tue', 'value': 84.72},
    {'day': 'Wed', 'value': 87.34},
    {'day': 'Thu', 'value': 81.67},
    {'day': 'Fri', 'value': 78.35},
    {'day': 'Sat', 'value': 22.4},
    {'day': 'Sun', 'value': 18.14}
];

export const PriceChart = () => {
    return (
        <div className="w-full h-[500px] p-4 bg-white rounded-lg shadow-sm mt-6">
            <h2 className="text-xl font-bold mb-4 text-center">Average Daily Consumption Profile</h2>
            <ResponsiveContainer width="100%" height="100%">
                <LineChart
                    data={data}
                    margin={{
                        top: 20,
                        right: 30,
                        left: 20,
                        bottom: 10,
                    }}
                >
                    <CartesianGrid strokeDasharray="3 3"/>
                    <XAxis
                        dataKey="day"
                        padding={{left: 30, right: 30}}
                    />
                    <YAxis label={{value: 'Average Load (kW)', angle: -90, position: 'insideLeft'}}/>
                    <Tooltip/>
                    <Legend/>
                    <Line
                        type="monotone"
                        dataKey="value"
                        stroke="#8884d8"
                        name="Avg Daily Load"
                        activeDot={{r: 8}}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}