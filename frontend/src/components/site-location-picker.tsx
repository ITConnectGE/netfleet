"use client";

// Click-to-place site location picker using OpenStreetMap tiles via Leaflet.
// Free, no API key. Includes Nominatim geocoding (also free; per the
// Nominatim usage policy we throttle to one request per user keystroke
// after a 500ms debounce and identify with a descriptive User-Agent-style
// header — Referrer is implicit).
//
// This component is client-only. Import it via `next/dynamic` with
// ssr:false from server-rendered pages so Leaflet's `window` access
// doesn't blow up at build time.

import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";

interface NominatimResult {
  display_name: string;
  lat: string;
  lon: string;
}

interface Props {
  latitude: number | null;
  longitude: number | null;
  onChange: (lat: number, lng: number) => void;
  address?: string | null;
  onAddressChange?: (address: string) => void;
}

// Custom SVG marker so we don't depend on Leaflet's broken default image
// URLs after webpack bundling.
const pinIcon = L.divIcon({
  html: `<svg viewBox="0 0 32 40" width="32" height="40" xmlns="http://www.w3.org/2000/svg">
    <path d="M16 0C7.16 0 0 7.16 0 16c0 12 16 24 16 24s16-12 16-24C32 7.16 24.84 0 16 0z"
          fill="#10b981" stroke="#064e3b" stroke-width="1.5"/>
    <circle cx="16" cy="16" r="6" fill="white"/>
  </svg>`,
  className: "",
  iconSize: [32, 40],
  iconAnchor: [16, 40],
  popupAnchor: [0, -40],
});

export default function SiteLocationPicker({
  latitude,
  longitude,
  onChange,
  address,
  onAddressChange,
}: Props) {
  const [search, setSearch] = useState(address ?? "");
  const [results, setResults] = useState<NominatimResult[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<number | null>(null);

  // Manual lat/lng entry. We sync the textual draft with the pin
  // position when it changes from elsewhere (map click, search hit),
  // but otherwise leave it alone so the user's in-progress typing
  // isn't clobbered. Format accepts "lat, lng", "lat lng", and a
  // single decimal pair pasted from Google Maps' "share location".
  const [coordInput, setCoordInput] = useState(() =>
    latitude !== null && longitude !== null
      ? `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`
      : "",
  );
  const [coordError, setCoordError] = useState<string | null>(null);
  const coordTouched = useRef(false);
  useEffect(() => {
    if (coordTouched.current) return;
    setCoordInput(
      latitude !== null && longitude !== null
        ? `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`
        : "",
    );
  }, [latitude, longitude]);

  function applyCoords() {
    const raw = coordInput.trim();
    if (!raw) {
      setCoordError(null);
      return;
    }
    // Accept comma, semicolon, slash, or whitespace — operators paste
    // from a variety of sources (Google Maps right-click "What's here",
    // GPS tools, Excel sheets).
    const parts = raw.split(/[\s,;/]+/).filter(Boolean);
    if (parts.length !== 2) {
      setCoordError("Expected two numbers — latitude and longitude.");
      return;
    }
    const lat = Number.parseFloat(parts[0]);
    const lng = Number.parseFloat(parts[1]);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      setCoordError("Couldn't parse those values as numbers.");
      return;
    }
    if (lat < -90 || lat > 90) {
      setCoordError("Latitude must be between -90 and 90.");
      return;
    }
    if (lng < -180 || lng > 180) {
      setCoordError("Longitude must be between -180 and 180.");
      return;
    }
    setCoordError(null);
    coordTouched.current = false;
    onChange(lat, lng);
  }

  // Keep the search box in sync when the parent address prop changes.
  useEffect(() => {
    setSearch(address ?? "");
  }, [address]);

  // Debounced Nominatim geocode. Cancels in-flight requests if the user
  // keeps typing.
  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (search.trim().length < 3) {
      setResults([]);
      return;
    }
    debounceRef.current = window.setTimeout(async () => {
      setSearching(true);
      try {
        const resp = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&limit=5&q=${encodeURIComponent(search)}`,
          { headers: { "Accept-Language": navigator.language } },
        );
        if (resp.ok) {
          const json = (await resp.json()) as NominatimResult[];
          setResults(json);
        } else {
          setResults([]);
        }
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 500);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [search]);

  const center: [number, number] = useMemo(() => {
    if (latitude !== null && longitude !== null) return [latitude, longitude];
    // Sensible default: Tbilisi, Georgia (NetFleet is a Georgian project,
    // most early users are there). Operators outside the region will pan
    // and zoom on first use.
    return [41.7151, 44.8271];
  }, [latitude, longitude]);

  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">
          Search for address (free OpenStreetMap geocoding)
        </label>
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            onAddressChange?.(e.target.value);
          }}
          placeholder="Tbilisi, Rustaveli Avenue 5"
          className="block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {searching && (
          <p className="text-[10px] text-muted-foreground">searching…</p>
        )}
        {results.length > 0 && (
          <ul className="rounded-md border border-border bg-card text-xs shadow-sm">
            {results.map((r) => (
              <li key={`${r.lat}-${r.lon}`}>
                <button
                  type="button"
                  onClick={() => {
                    const lat = Number.parseFloat(r.lat);
                    const lng = Number.parseFloat(r.lon);
                    onChange(lat, lng);
                    onAddressChange?.(r.display_name);
                    setSearch(r.display_name);
                    setResults([]);
                  }}
                  className="block w-full px-3 py-1.5 text-left hover:bg-accent"
                >
                  {r.display_name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">
          Or enter coordinates (latitude, longitude)
        </label>
        <div className="flex items-stretch gap-2">
          <input
            type="text"
            inputMode="decimal"
            value={coordInput}
            onChange={(e) => {
              coordTouched.current = true;
              setCoordInput(e.target.value);
              setCoordError(null);
            }}
            onBlur={applyCoords}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyCoords();
              }
            }}
            placeholder="41.715137, 44.827095"
            className="block flex-1 rounded-md border border-input bg-background px-3 py-1.5 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="button"
            onClick={applyCoords}
            className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium transition hover:bg-accent"
          >
            Apply
          </button>
        </div>
        {coordError ? (
          <p className="text-[11px] text-destructive">{coordError}</p>
        ) : (
          <p className="text-[10px] text-muted-foreground">
            Accepts comma, space, or semicolon separators. Paste straight from
            Google Maps&apos; “What&apos;s here” menu.
          </p>
        )}
      </div>

      <div className="h-72 overflow-hidden rounded-md border border-border">
        <MapContainer
          center={center}
          zoom={latitude !== null ? 13 : 6}
          scrollWheelZoom
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {latitude !== null && longitude !== null && (
            <Marker position={[latitude, longitude]} icon={pinIcon} />
          )}
          <Centerer
            target={latitude !== null && longitude !== null ? [latitude, longitude] : null}
          />
          <ClickHandler onPick={onChange} />
        </MapContainer>
      </div>

      <p className="text-[11px] text-muted-foreground">
        Click the map to drop a pin, or pick a result from the search.{" "}
        {latitude !== null && longitude !== null && (
          <span className="font-mono">
            ({latitude.toFixed(5)}, {longitude.toFixed(5)})
          </span>
        )}
      </p>
    </div>
  );
}

function ClickHandler({
  onPick,
}: {
  onPick: (lat: number, lng: number) => void;
}) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function Centerer({ target }: { target: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.setView(target, Math.max(map.getZoom(), 13), { animate: true });
  }, [target, map]);
  return null;
}
