import React, { useState, useEffect } from 'react';
import backgroundImage from './bg.webp';
import { DataForm } from './components/DataForm';
import {ConsumptionChart} from "./components/Chart";
import {PriceChart} from "./components/charts/Price";

const App = () =>  {
    const handleFormSubmit = (data: any) => {
        console.log('Form submitted:', data)
    };

    const [data, setData] = useState();

    useEffect(() => {
        const fetchData = async () => {
            const res = await fetch(
                "http://127.0.0.1:8000/api/benefits?client_name=Client_A&run_name=2024_Q1_Analysis"
            );
            const json = await res.json();
            setData(json);
        };
        fetchData();
    }, []);

    console.log('Data:', data)

    return (
        <div style={{
            backgroundImage: `url(${backgroundImage})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            minHeight: "100vh",
        }}>
            <DataForm onSubmit={handleFormSubmit} />
            <div className="w-[70%] mx-auto">
                <ConsumptionChart/>
                <PriceChart/>
            </div>

        </div>
    );
}

export default App;