import React, {useState, useEffect} from 'react';
import backgroundImage from './bg.webp';
import {DataForm} from './components/DataForm';
import {WeeklyHighResChart} from "./components/charts/WeeklyLoadConsumption";
import BenefitWaterfall from "./components/charts/Waterfall";

const App = () => {
    const [chartData, setChartData] = useState(null);

    // CSV Processing Logic (Moved to Parent)
    const processCSV = (csvText: string) => {
        const lines = csvText.split('\n');
        const rows = lines.slice(1).filter(line => line.trim() !== '');

        // Initialize 7 days * 24 hours * 4 quarters
        const stats = new Array(7).fill(0).map(() =>
            new Array(24).fill(0).map(() =>
                new Array(4).fill(0).map(() => ({sum: 0, count: 0}))
            )
        );

        rows.forEach(row => {
            const cols = row.split(',');
            if (cols.length < 2) return;
            const date = new Date(cols[0]);
            const val = parseFloat(cols[1]);

            if (!isNaN(date.getTime()) && !isNaN(val)) {
                // Adjust to Mon(0) - Sun(6)
                let dayIdx = date.getDay() - 1;
                if (dayIdx === -1) dayIdx = 6;
                const h = date.getHours();
                const q = Math.floor(date.getMinutes() / 15);
                if (dayIdx >= 0 && dayIdx < 7) {
                    stats[dayIdx][h][q].sum += val;
                    stats[dayIdx][h][q].count += 1;
                }
            }
        });

        // Flatten
        const flatData: ChartDataPoint[] = [];
        const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        let globalIndex = 0;

        for (let d = 0; d < 7; d++) {
            for (let h = 0; h < 24; h++) {
                for (let q = 0; q < 4; q++) {
                    const {sum, count} = stats[d][h][q];
                    flatData.push({
                        day: dayNames[d],
                        time: `${h.toString().padStart(2, '0')}:${(q * 15).toString().padStart(2, '0')}`,
                        value: count > 0 ? parseFloat((sum / count).toFixed(2)) : 0,
                        globalIndex: globalIndex++
                    });
                }
            }
        }
        setChartData(flatData);
    };

    const handleFileSelect = (file: File) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const text = e.target?.result as string;
            processCSV(text);
        };
        reader.readAsText(file);
    };

    return (
        <div className="pb-20" style={{
            backgroundImage: `url(${backgroundImage})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            minHeight: "100vh",
        }}>
            <DataForm onSubmit={(data) => console.log("Submitting:", data)}
                      onFileSelect={handleFileSelect}/>
            <WeeklyHighResChart data={chartData}/>

            <div className="block w-full">
            <BenefitWaterfall/>
            </div>
        </div>
    );
}

export default App;