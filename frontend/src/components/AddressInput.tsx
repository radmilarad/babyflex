import React, { useState, useEffect, useRef } from "react";
import {VITE_API_URL} from "../../config";

interface AddressInputProps {
    onGridFeeFetched?: (data: any) => void;
}

const AddressInput: React.FC<AddressInputProps> = ({ onGridFeeFetched }) => {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState<any[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [loading, setLoading] = useState(false);
    const [fetchingGridFee, setFetchingGridFee] = useState(false);

    const [gridFee, setGridFee] = useState<{
        arbeitspreis: number | null;
        leistungspreis: number | null;
    } | null>(null);

    const isSelectingRef = useRef(false);
    const ignoreFetchRef = useRef(false);

    // 🔍 Fetch address suggestions
    useEffect(() => {
        if (ignoreFetchRef.current) {
            ignoreFetchRef.current = false;
            return;
        }

        const controller = new AbortController();
        const { signal } = controller;

        const fetchAddresses = async () => {
            if (query.length < 3) {
                setResults([]);
                setShowDropdown(false);
                return;
            }

            setLoading(true);
            try {
                const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(
                    query
                )}&limit=5&lang=de`;
                const res = await fetch(url, { signal });
                const data = await res.json();

                if (!signal.aborted) {
                    setResults(data.features || []);
                    setShowDropdown(true);
                }
            } catch (err: any) {
                if (err.name !== "AbortError") console.error(err);
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

    // ⚡ Fetch grid data
    const fetchGridData = async (
        postCode: string,
        city: string,
        street: string,
        houseNumber: string
    ) => {
        try {
            setGridFee(null);
            setFetchingGridFee(true);

            const params = new URLSearchParams({
                postCode,
                location: city,
                street,
                houseNumber,
                yearlyConsumption: "150000",
                maxPeak: "50",
            });

            console.log("📡 Fetching Grid Data for:", params.toString());
            const res = await fetch(
                `${VITE_API_URL}/enet-gridfee?${params.toString()}`
            );

            if (!res.ok) {
                console.error("API Error Status:", res.status);
                return;
            }

            const data = await res.json();
            if (data.error) {
                console.error("Grid fee API error:", data);
            } else {
                const prices = data.spezifischePreise || [];
                const apObj = prices.find(
                    (p: any) => p.typ === "ARBEITSPREIS_WIRKARBEIT"
                );
                const lpObj = prices.find(
                    (p: any) => p.typ === "LEISTUNGSPREIS_WIRKLEISTUNG"
                );

                const extractedData = {
                    arbeitspreis: apObj ? Number(apObj.wert) : 0,
                    leistungspreis: lpObj ? Number(lpObj.wert) : 0,
                };

                setGridFee(extractedData);
                onGridFeeFetched?.(extractedData);
            }
        } catch (err) {
            console.error("❌ Error fetching grid fee data:", err);
        } finally {
            setFetchingGridFee(false);
        }
    };

    // 🏠 Handle address selection
    const selectAddress = (result: any) => {
        ignoreFetchRef.current = true;

        const props = result.properties;
        const displayName = `${props.name || props.street || ""} ${
            props.housenumber || ""
        }, ${props.postcode || ""} ${props.city || props.town || ""}`;

        setQuery(displayName);
        setShowDropdown(false);

        const postCode = props.postcode || "";
        const city = props.city || props.town || props.village || "";
        const street = props.street || props.name || "";
        const houseNumber = props.housenumber || "1";

        fetchGridData(postCode, city, street, houseNumber);
    };

    const handleBlur = () => {
        setTimeout(() => {
            if (isSelectingRef.current) return;
            setShowDropdown(false);
        }, 200);
    };

    return (
        <div className="relative w-full">
            {/* Address Input */}
            <input
                type="text"
                value={query}
                onChange={(e) => {
                    setQuery(e.target.value);
                    if (!showDropdown && e.target.value.length >= 3)
                        setShowDropdown(true);
                }}
                onBlur={handleBlur}
                placeholder="Adresse eingeben (z.B. Musterstraße 1, Berlin)"
                className="w-full rounded-md border border-gray-200 bg-white px-4 py-2.5 text-gray-900 focus:border-emerald-500 focus:ring-emerald-500 outline-none transition-all shadow-sm sm:text-sm"
            />

            {/* Spinner inside input */}
            {loading && (
                <div className="absolute right-3 top-2.5 text-gray-400 animate-spin">
                    <svg
                        className="w-5 h-5"
                        fill="none"
                        viewBox="0 0 24 24"
                    >
                        <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                        ></circle>
                        <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        ></path>
                    </svg>
                </div>
            )}

            {/* Address Suggestions */}
            {showDropdown && results.length > 0 && (
                <ul className="absolute z-50 bg-white border border-gray-200 rounded-md mt-1 w-full max-h-60 overflow-y-auto shadow-xl">
                    {results.map((r, i) => (
                        <li
                            key={i}
                            onMouseDown={() => {
                                isSelectingRef.current = true;
                                selectAddress(r);
                                setTimeout(() => {
                                    isSelectingRef.current = false;
                                }, 300);
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

            {/* Loader or Grid Fee Display */}
            <div
                className={`transition-all duration-500 ease-in-out ${
                    fetchingGridFee || gridFee ? "mt-4 min-h-[90px]" : "mt-1 min-h-[0px]"
                } flex flex-col items-center justify-center`}
            >
                {fetchingGridFee && (
                    <div className="flex flex-col items-center text-gray-600 animate-pulse">
                        <div className="w-5 h-5 border-2 border-emerald-300 border-t-emerald-600 rounded-full animate-spin mb-2"></div>
                        <span className="text-sm">Netzentgelte werden geladen...</span>
                    </div>
                )}

                {!fetchingGridFee && gridFee && (
                    <div className="grid grid-cols-2 gap-3 w-full animate-in fade-in slide-in-from-top-1 duration-300">
                        <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100 text-center">
                            <p className="text-[10px] text-emerald-600 font-medium uppercase tracking-wide">
                                Arbeitspreis
                            </p>
                            <p className="text-xl font-bold text-gray-900">
                                {gridFee.arbeitspreis?.toFixed(2) ?? "-"}{" "}
                                <span className="text-sm font-normal text-gray-500">
                  ct/kWh
                </span>
                            </p>
                        </div>
                        <div className="p-3 bg-blue-50 rounded-lg border border-blue-100 text-center">
                            <p className="text-[10px] text-blue-600 font-medium uppercase tracking-wide">
                                Leistungspreis
                            </p>
                            <p className="text-xl font-bold text-gray-900">
                                {gridFee.leistungspreis?.toFixed(2) ?? "-"}{" "}
                                <span className="text-sm font-normal text-gray-500">€/kW</span>
                            </p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default AddressInput;
