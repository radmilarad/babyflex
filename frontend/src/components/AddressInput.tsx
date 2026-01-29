import React, { useState, useEffect, useRef } from "react";

interface AddressInputProps {
    onGridFeeFetched?: (data: any) => void;
}

const AddressInput: React.FC<AddressInputProps> = ({ onGridFeeFetched }) => {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<any[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [loading, setLoading] = useState(false);
    const [gridFee, setGridFee] = useState<{ arbeitspreis: number | null; leistungspreis: number | null } | null>(null);

    // Ref to track if we are currently clicking a dropdown item to prevent onBlur conflict
    const isSelectingRef = useRef(false);

    useEffect(() => {
        const controller = new AbortController();
        const { signal } = controller;

        const fetchAddresses = async () => {
            if (query.length < 3) return;
            setLoading(true);

            try {
                // Using Photon (fast)
                const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&limit=5&lang=de`;
                const res = await fetch(url, { signal });
                const data = await res.json();
                setResults(data.features || []);
                setShowDropdown(true);
            } catch (err: any) {
                if (err.name !== 'AbortError') console.error(err);
            } finally {
                if (!signal.aborted) setLoading(false);
            }
        };

        const delayDebounce = setTimeout(fetchAddresses, 300);
        return () => {
            clearTimeout(delayDebounce);
            controller.abort();
        };
    }, [query]);

    // ⚡ Reusable function to fetch backend data
    const fetchGridData = async (postCode: string, city: string, street: string, houseNumber: string) => {
        try {
            // Clear old data while loading new data
            setGridFee(null);

            const params = new URLSearchParams({
                postCode,
                location: city,
                street,
                houseNumber,
                yearlyConsumption: "150000",
                maxPeak: "50",
            });

            const res = await fetch(`http://127.0.0.1:8000/api/enet-gridfee?${params.toString()}`);
            const data = await res.json();

            if (data.error) {
                console.error("Grid fee API error:", data);
            } else {
                // Extract only what we need
                const prices = data.spezifischePreise || [];
                const apObj = prices.find((p: any) => p.typ === "ARBEITSPREIS_WIRKARBEIT");
                const lpObj = prices.find((p: any) => p.typ === "LEISTUNGSPREIS_WIRKLEISTUNG");

                const extractedData = {
                    arbeitspreis: apObj ? apObj.wert : null,
                    leistungspreis: lpObj ? lpObj.wert : null
                };

                console.log("✅ Fetched Grid Fee:", extractedData);
                setGridFee(extractedData);
                onGridFeeFetched?.(extractedData);
            }
        } catch (err) {
            console.error("Error fetching grid fee data:", err);
        }
    };

    // 🧩 Central logic to parse a Photon result and trigger fetch
    const selectAddress = (result: any) => {
        const props = result.properties;
        const displayName = `${props.name || ''}, ${props.street || ''} ${props.housenumber || ''}, ${props.city || props.town || ''}`;

        setQuery(displayName);
        setShowDropdown(false);

        // Normalize data
        const postCode = props.postcode || "";
        const city = props.city || props.town || props.village || "";
        const street = props.street || props.name || "";
        const houseNumber = props.housenumber || "1";

        fetchGridData(postCode, city, street, houseNumber);
    };

    // 🖱️ Event: User types manually
    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setQuery(e.target.value);
        // Important: Clear old result when user edits text
        if (gridFee) setGridFee(null);
    };

    // 🖱️ Event: User clicks outside (Blur) or hits Enter
    const handleBlur = () => {
        // Allow a small delay to see if the user actually clicked the dropdown
        setTimeout(() => {
            if (isSelectingRef.current) return; // Addressed handled by onMouseDown

            // If user leaves field, has results, but no gridFee yet -> Auto-select top result
            if (results.length > 0 && !gridFee && query.length > 3) {
                console.log("Blur triggered auto-select");
                selectAddress(results[0]);
            }
            setShowDropdown(false);
        }, 200);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && results.length > 0) {
            selectAddress(results[0]);
            e.preventDefault(); // Prevent form submit if inside a form
        }
    };

    return (
        <div className="relative w-full mx-auto">
            <input
                type="text"
                value={query}
                onChange={handleInputChange}
                onBlur={handleBlur}
                onKeyDown={handleKeyDown}
                placeholder="Adresse eingeben (z.B. Musterstraße 1, Berlin)"
                className="w-full rounded-md border border-gray-300 bg-white px-4 py-3 text-gray-900 focus:border-emerald-500 focus:ring-emerald-500 outline-none transition-all"
            />

            {loading && <div className="absolute right-3 top-3 text-gray-400 text-sm">⏳</div>}

            {showDropdown && results.length > 0 && (
                <ul className="absolute z-50 bg-white border border-gray-200 rounded-md mt-1 w-full max-h-60 overflow-y-auto shadow-lg">
                    {results.map((r, i) => (
                        <li
                            key={i}
                            // Use onMouseDown instead of onClick to fire BEFORE onBlur
                            onMouseDown={() => {
                                isSelectingRef.current = true;
                                selectAddress(r);
                                // Reset ref after a moment
                                setTimeout(() => { isSelectingRef.current = false; }, 300);
                            }}
                            className="px-4 py-2 hover:bg-emerald-50 cursor-pointer text-sm text-gray-800 border-b border-gray-100 last:border-0"
                        >
                            <div className="font-medium">
                                {r.properties.name} {r.properties.housenumber}
                            </div>
                            <div className="text-xs text-gray-500">
                                {r.properties.postcode} {r.properties.city}
                            </div>
                        </li>
                    ))}
                </ul>
            )}

            {/* Result Display */}
            {gridFee && (
                <div className="mt-6 grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2 duration-300">
                    <div className="p-4 bg-emerald-50 rounded-lg border border-emerald-100 text-center">
                        <p className="text-xs text-emerald-600 font-medium uppercase tracking-wide">Arbeitspreis</p>
                        <p className="text-2xl font-bold text-gray-900">
                            {gridFee.arbeitspreis?.toFixed(2) ?? "-"} <span className="text-sm font-normal text-gray-500">ct/kWh</span>
                        </p>
                    </div>
                    <div className="p-4 bg-blue-50 rounded-lg border border-blue-100 text-center">
                        <p className="text-xs text-blue-600 font-medium uppercase tracking-wide">Leistungspreis</p>
                        <p className="text-2xl font-bold text-gray-900">
                            {gridFee.leistungspreis?.toFixed(2) ?? "-"} <span className="text-sm font-normal text-gray-500">€/kW</span>
                        </p>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AddressInput;
