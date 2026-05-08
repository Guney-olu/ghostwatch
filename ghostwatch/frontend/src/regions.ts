export type RegionCategory = "CHOKEPOINT" | "IUU" | "STRATEGIC" | "PORT";

export interface MonitorRegion {
  id: string;
  category: RegionCategory;
  flag: string;
  name: string;
  subtitle: string;
  lon: number;
  lat: number;
  timestamp: string;
  size_km: number;
}

// size_km is intentionally small (1-2 km). The fine-tuned VLM was trained on
// Sentinel-2 imagery (10 m/px native) downsized to 384 px on the long edge,
// so each pixel covers (size_km * 1000) / 384 m. At 1.5 km that's ~4 m/px —
// boats (20-40 m long) appear as 5-10 px, the smallest the model reliably
// localizes. Larger boxes turn boats into single dots.

export const REGIONS: MonitorRegion[] = [
  // ── Global chokepoints — guaranteed vessel traffic ─────────────────────
  {
    id: "singapore",
    category: "CHOKEPOINT",
    flag: "🇸🇬",
    name: "Strait of Singapore",
    subtitle: "Busiest shipping lane on Earth · ~80k transits/yr",
    lon: 103.82, lat: 1.25,
    timestamp: "2025-03-15T03:00:00Z", size_km: 1.5,
  },
  {
    id: "malacca",
    category: "CHOKEPOINT",
    flag: "🇲🇾",
    name: "Strait of Malacca",
    subtitle: "Indo–Pacific trade artery · oil & container traffic",
    lon: 100.40, lat: 2.95,
    timestamp: "2025-04-10T03:00:00Z", size_km: 1.5,
  },
  {
    id: "suez",
    category: "CHOKEPOINT",
    flag: "🇪🇬",
    name: "Suez Canal Approach",
    subtitle: "12% of global trade transits here",
    lon: 32.55, lat: 30.0,
    timestamp: "2025-05-01T08:00:00Z", size_km: 1.5,
  },
  {
    id: "hormuz",
    category: "CHOKEPOINT",
    flag: "🇦🇪",
    name: "Strait of Hormuz",
    subtitle: "30% of seaborne oil · sanctions evasion hotspot",
    lon: 56.25, lat: 26.55,
    timestamp: "2025-06-12T07:00:00Z", size_km: 1.5,
  },
  {
    id: "channel",
    category: "CHOKEPOINT",
    flag: "🇬🇧",
    name: "English Channel · Dover",
    subtitle: "500+ ship transits per day",
    lon: 1.35, lat: 50.95,
    timestamp: "2025-06-15T10:00:00Z", size_km: 1.5,
  },
  {
    id: "gibraltar",
    category: "CHOKEPOINT",
    flag: "🇪🇸",
    name: "Strait of Gibraltar",
    subtitle: "Mediterranean gateway · drug trafficking corridor",
    lon: -5.35, lat: 35.95,
    timestamp: "2025-07-01T09:00:00Z", size_km: 1.5,
  },
  {
    id: "bosphorus",
    category: "CHOKEPOINT",
    flag: "🇹🇷",
    name: "Bosphorus Strait",
    subtitle: "Black Sea corridor · grain & oil",
    lon: 28.97, lat: 41.10,
    timestamp: "2025-05-20T08:00:00Z", size_km: 1.2,
  },

  // ── IUU fishing & sanctions evasion ─────────────────────────────────────
  {
    id: "galapagos",
    category: "IUU",
    flag: "🇪🇨",
    name: "Galápagos EEZ Edge",
    subtitle: "Chinese distant-water fleet incursions",
    lon: -85.50, lat: -1.0,
    timestamp: "2025-08-15T15:00:00Z", size_km: 2.0,
  },
  {
    id: "argentina",
    category: "IUU",
    flag: "🇦🇷",
    name: "Argentine EEZ · Puerto Madryn",
    subtitle: "Chinese squid jiggers · 'milky seas' visible from space",
    lon: -62.50, lat: -42.50,
    timestamp: "2025-02-10T18:00:00Z", size_km: 2.0,
  },
  {
    id: "guinea",
    category: "IUU",
    flag: "🇸🇱",
    name: "West African Coast · Sierra Leone",
    subtitle: "$2B/yr in illegal fishing losses",
    lon: -13.20, lat: 8.50,
    timestamp: "2025-06-05T11:00:00Z", size_km: 1.5,
  },
  {
    id: "nkorea",
    category: "IUU",
    flag: "🇰🇵",
    name: "North Korean Coast · Wonsan",
    subtitle: "UN sanctions evasion · ship-to-ship transfers",
    lon: 127.45, lat: 39.18,
    timestamp: "2025-04-22T02:00:00Z", size_km: 1.5,
  },

  // ── Strategic tension zones ─────────────────────────────────────────────
  {
    id: "spratly",
    category: "STRATEGIC",
    flag: "🇨🇳",
    name: "Spratly Islands · South China Sea",
    subtitle: "Maritime militia · contested sovereignty",
    lon: 114.35, lat: 9.85,
    timestamp: "2025-03-20T03:00:00Z", size_km: 2.0,
  },
  {
    id: "taiwan",
    category: "STRATEGIC",
    flag: "🇹🇼",
    name: "Taiwan Strait · Kaohsiung",
    subtitle: "PLA Navy exercise zone",
    lon: 120.30, lat: 22.55,
    timestamp: "2025-04-18T03:00:00Z", size_km: 1.5,
  },
  {
    id: "crimea",
    category: "STRATEGIC",
    flag: "🇺🇦",
    name: "Crimea Coast · Sevastopol",
    subtitle: "Russian Black Sea Fleet anchorage",
    lon: 33.55, lat: 44.60,
    timestamp: "2025-05-08T08:00:00Z", size_km: 1.2,
  },

  // ── Major commercial ports ──────────────────────────────────────────────
  {
    id: "rotterdam",
    category: "PORT",
    flag: "🇳🇱",
    name: "Port of Rotterdam",
    subtitle: "Largest port in Europe",
    lon: 4.05, lat: 51.95,
    timestamp: "2025-07-01T10:00:00Z", size_km: 1.0,
  },
  {
    id: "shanghai",
    category: "PORT",
    flag: "🇨🇳",
    name: "Port of Shanghai",
    subtitle: "World's busiest container port",
    lon: 121.85, lat: 31.10,
    timestamp: "2025-04-15T03:00:00Z", size_km: 1.2,
  },
  {
    id: "longbeach",
    category: "PORT",
    flag: "🇺🇸",
    name: "LA / Long Beach",
    subtitle: "Largest US container gateway",
    lon: -118.21, lat: 33.75,
    timestamp: "2025-07-01T19:00:00Z", size_km: 1.0,
  },
];

export const CATEGORY_LABELS: Record<RegionCategory, string> = {
  CHOKEPOINT: "Maritime Chokepoint",
  IUU: "Illegal Fishing Zone",
  STRATEGIC: "Strategic Interest",
  PORT: "Commercial Port",
};

export const CATEGORY_COLORS: Record<RegionCategory, string> = {
  CHOKEPOINT: "#60a5fa",
  IUU: "#f87171",
  STRATEGIC: "#fbbf24",
  PORT: "#34d399",
};
