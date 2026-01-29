import React, { useState, ChangeEvent, FormEvent } from 'react';
import AddressInput from "./AddressInput";

interface FormData {
    value1: number | '';
    value2: number | '';
    value3: number | '';
    file: File | null;
    privacyAccepted: boolean;
}

interface DataFormProps {
    onSubmit?: (data: FormData) => void;
}

export const DataForm: React.FC<DataFormProps> = ({ onSubmit }) => {
    const [formData, setFormData] = useState<FormData>({
        value1: '',
        value2: '',
        value3: '',
        file: null,
        privacyAccepted: false,
    });

    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
        const { name, value, type, checked } = e.target;
        setFormData({
            ...formData,
            [name]: type === 'checkbox' ? checked : type === 'number' ? Number(value) : value,
        });
    };

    const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0] || null;
        setFormData({ ...formData, file });
    };

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (onSubmit) onSubmit(formData);
    };

    const labelStyle = "block text-base font-normal text-gray-900 mb-2";
    const inputStyle = "block w-full rounded-md border border-gray-300 bg-white px-4 py-3 text-gray-900 focus:border-gray-500 focus:ring-1 focus:ring-gray-500 outline-none transition-all";

    return (
        <div className="w-full h-full flex flex-col items-center justify-center py-12 px-4">

            <h1 className="text-4xl md:text-5xl font-bold text-white mb-8 tracking-tight drop-shadow-md">
                Trawa flex
            </h1>

            <form
                onSubmit={handleSubmit}
                className="w-full max-w-2xl bg-gray-50/95 backdrop-blur-sm rounded-xl p-8 sm:p-10 shadow-2xl"
            >

                <div className="grid grid-cols-1 gap-6 mb-6">
                    <div>
                        <label htmlFor="value1" className={labelStyle}>PV power</label>
                        <input
                            type="number"
                            name="value1"
                            id="value1"
                            value={formData.value1}
                            onChange={handleChange}
                            className={inputStyle}
                            placeholder="0.00"
                            required
                        />
                    </div>
                </div>

                {/* Full Width: Value 3 */}
                <div className="mb-6">
                    <label htmlFor="value3" className={labelStyle}>Battery type - make it a dropdown</label>
                    <input
                        type="number"
                        name="value3"
                        id="value3"
                        value={formData.value3}
                        onChange={handleChange}
                        className={inputStyle}
                        placeholder="0.00"
                        required
                    />
                </div>

                <div className="mb-6">
                    <label htmlFor="value3" className={labelStyle}>Address</label>
                    <AddressInput/>
                </div>

                {/* File Upload */}
                <div className="mb-8">
                <label htmlFor="file" className={labelStyle}>Upload CSV Data</label>
                    <input
                        type="file"
                        name="file"
                        id="file"
                        accept=".csv"
                        onChange={handleFileChange}
                        className={`${inputStyle} file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 cursor-pointer`}
                        required
                    />
                </div>

                {/* Submit Button */}
                <button
                    type="submit"
                    className="w-full rounded-md bg-[#2D2D2D] text-white text-lg py-3.5 font-medium hover:bg-black transition-colors shadow-sm"
                >
                    Submit Data
                </button>
            </form>
        </div>
    );

};