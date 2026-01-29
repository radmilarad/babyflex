import React, { useState, useEffect } from "react";

interface AddressInputProps {
    onGridFeeFetched?: (data: any) => void;
}

const AddressInput: React.FC<AddressInputProps> = ({ onGridFeeFetched }) => {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<any[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [loading, setLoading] = useState(false);
    const [gridFee, setGridFee] = useState<any>(null);

    // 📍 Fetch address suggestions from Nominatim
    useEffect(() => {
        const fetchAddresses = async () => {
            if (query.length < 3) return;
            setLoading(true);

            try {
                const url = `https://nominatim.openstreetmap.org/search?format=json&countrycodes=de&addressdetails=1&limit=5&q=${encodeURIComponent(
                    query
                )}`;
                const res = await fetch(url, {
                    headers: { "User-Agent": "TrawaFlexApp/1.0" },
                });
                const data = await res.json();
                setResults(data);
                setShowDropdown(true);
            } catch (err) {
                console.error("Error fetching address suggestions:", err);
            } finally {
                setLoading(false);
            }
        };

        const delayDebounce = setTimeout(fetchAddresses, 400);
        return () => clearTimeout(delayDebounce);
    }, [query]);

    // 🧩 Handle address selection
    const handleSelect = async (result: any) => {
        setQuery(result.display_name);
        setShowDropdown(false);

        const address = result.address || {};
        const postCode = address.postcode || "";
        const city = address.city || address.town || address.village || "";
        const street = address.road || "";
        const houseNumber = address.house_number || "1"; // fallback

        console.log("📍 Selected address:", {
            postCode,
            city,
            street,
            houseNumber,
        });

        // ⚡ Call your FastAPI backend to fetch grid fees
        try {
            const params = new URLSearchParams({
                postCode,
                location: city,
                street,
                houseNumber,
                yearlyConsumption: "150000", // example fixed values
                maxPeak: "50",
            });

            const res = await fetch(`http://127.0.0.1:8000/api/enet-gridfee?${params.toString()}`);
            const data = await res.json();

            if (data.error) {
                console.error("Grid fee API error:", data);
            } else {
                console.log("✅ Grid fee data:", data);
                setGridFee(data);
                onGridFeeFetched?.(data);
            }
        } catch (err) {
            console.error("Error fetching grid fee data:", err);
        }
    };

    return (
        <div className="relative w-full max-w-lg mx-auto">
            <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Adresse eingeben..."
                className="w-full rounded-md border border-gray-300 bg-white px-4 py-3 text-gray-900 focus:border-emerald-500 focus:ring-emerald-500 outline-none"
            />

            {loading && (
                <div className="absolute right-3 top-3 text-gray-400 text-sm">⏳</div>
            )}

            {showDropdown && results.length > 0 && (
                <ul className="absolute z-50 bg-white border border-gray-200 rounded-md mt-1 w-full max-h-60 overflow-y-auto shadow-lg">
                    {results.map((r, i) => (
                        <li
                            key={i}
                            onClick={() => handleSelect(r)}
                            className="px-4 py-2 hover:bg-emerald-50 cursor-pointer text-sm text-gray-800"
                        >
                            {r.display_name}
                        </li>
                    ))}
                </ul>
            )}

            {/* Optional: Display grid fee data */}
            {gridFee && (
                <div className="mt-6 p-4 bg-white/70 rounded-lg shadow-sm text-gray-800">
                    <h3 className="font-semibold mb-2 text-lg">Netzentgelt (Grid Fee)</h3>
                    <pre className="text-sm overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(gridFee, null, 2)}
          </pre>
                </div>
            )}
        </div>
    );
};

export default AddressInput;
