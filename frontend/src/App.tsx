import React from 'react';
import backgroundImage from './bg.webp';
import { DataForm } from './components/DataForm';
import { ConsumptionChart } from "./components/charts/Line";
import {PriceChart} from "./components/charts/Price";

const App = () =>  {
    const handleFormSubmit = (data: any) => {
        console.log('Form submitted:', data)
    };
    return (
        <div style={{
            backgroundImage: `url(${backgroundImage})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            minHeight: "100vh",
        }}>
            <DataForm onSubmit={handleFormSubmit} />
            <div className="w-[70%] mx-auto">
                {/*<ConsumptionChart/>*/}
                {/*<PriceChart/>*/}
            </div>

        </div>
    );
}

export default App;