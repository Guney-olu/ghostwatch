"""Synthetic AIS data generator for ghost vessel demo scenarios.

Generates deterministic, plausible vessel tracking data for any maritime region.
Some vessels are intentionally marked as AIS-dark to create ghost vessel scenarios.
"""

import hashlib
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from ghostwatch import config


@dataclass
class AISVessel:
    mmsi: str
    vessel_name: str
    vessel_type: str
    lat: float
    lon: float
    heading: float
    speed_knots: float
    ais_status: str


_VESSEL_NAMES = [
    "Pacific Trader", "Ocean Pioneer", "Star Navigator", "Blue Horizon",
    "Northern Spirit", "Eastern Pearl", "Golden Wave", "Silver Moon",
    "Iron Dragon", "Sea Fortune", "Crystal Bay", "Thunder Storm",
    "Coral Queen", "Neptune's Call", "Wind Rider", "Deep Current",
    "Red Phoenix", "Jade Emperor", "Arctic Fox", "Desert Rose",
    "Shadow Runner", "Dawn Breaker", "Night Hawk", "Storm Chaser",
    "Harbor King", "Emerald Coast", "Viking Pride", "Atlas Venture",
]

_VESSEL_TYPES = [
    "cargo_ship", "tanker", "fishing_boat", "container_ship",
    "bulk_carrier", "patrol_vessel", "tugboat", "passenger_ferry",
]


class SyntheticAISFeed:
    """Generates synthetic AIS vessel data for a given maritime region."""

    def __init__(self, scenario_file: str | None = None):
        self._scenarios: dict[str, list[dict]] = {}
        if scenario_file and Path(scenario_file).exists():
            with open(scenario_file) as f:
                self._scenarios = json.load(f)

    def get_vessels_in_region(
        self,
        lon_min: float,
        lat_min: float,
        lon_max: float,
        lat_max: float,
    ) -> list[AISVessel]:
        """Get AIS vessels in a geographic bounding box.

        Returns deterministic results for the same region (seeded by coordinates).
        Some vessels will have ais_status='dark' — these won't appear in AIS
        but may be detected visually by the satellite.
        """
        scenario_vessels = self._check_scenario(lon_min, lat_min, lon_max, lat_max)
        if scenario_vessels is not None:
            return scenario_vessels

        return self._generate_vessels(lon_min, lat_min, lon_max, lat_max)

    def _check_scenario(
        self, lon_min: float, lat_min: float, lon_max: float, lat_max: float
    ) -> list[AISVessel] | None:
        """Check if coordinates fall within a pre-defined demo scenario."""
        for _name, scenario in self._scenarios.items():
            if not isinstance(scenario, dict):
                continue
            region = scenario.get("region", {})
            r_lon_min = region.get("lon_min", -180)
            r_lat_min = region.get("lat_min", -90)
            r_lon_max = region.get("lon_max", 180)
            r_lat_max = region.get("lat_max", 90)

            if (lon_min <= r_lon_max and lon_max >= r_lon_min and
                    lat_min <= r_lat_max and lat_max >= r_lat_min):
                return [
                    AISVessel(**v) for v in scenario.get("vessels", [])
                ]
        return None

    def _generate_vessels(
        self, lon_min: float, lat_min: float, lon_max: float, lat_max: float
    ) -> list[AISVessel]:
        """Generate deterministic synthetic vessels for a region."""
        seed_str = f"{lon_min:.2f},{lat_min:.2f},{lon_max:.2f},{lat_max:.2f}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        area_deg2 = abs(lon_max - lon_min) * abs(lat_max - lat_min)
        base_count = max(1, int(area_deg2 * 100))
        num_vessels = rng.randint(max(2, base_count - 2), base_count + 3)
        num_vessels = min(num_vessels, 8)

        vessels = []
        used_names = set()

        for i in range(num_vessels):
            name = rng.choice(_VESSEL_NAMES)
            while name in used_names:
                name = rng.choice(_VESSEL_NAMES)
            used_names.add(name)

            vessel_type = rng.choice(_VESSEL_TYPES)

            lat = rng.uniform(lat_min, lat_max)
            lon = rng.uniform(lon_min, lon_max)

            dark_roll = rng.random()
            if dark_roll < config.AIS_DARK_PROBABILITY:
                ais_status = "dark"
            elif dark_roll < config.AIS_DARK_PROBABILITY + 0.1:
                ais_status = "intermittent"
            else:
                ais_status = "active"

            vessels.append(AISVessel(
                mmsi=f"{rng.randint(200000000, 799999999)}",
                vessel_name=name,
                vessel_type=vessel_type,
                lat=round(lat, 6),
                lon=round(lon, 6),
                heading=round(rng.uniform(0, 360), 1),
                speed_knots=round(rng.uniform(0, 18), 1),
                ais_status=ais_status,
            ))

        return vessels

    def get_active_vessels(
        self, lon_min: float, lat_min: float, lon_max: float, lat_max: float
    ) -> list[AISVessel]:
        """Get only vessels that are broadcasting AIS (not dark)."""
        all_vessels = self.get_vessels_in_region(lon_min, lat_min, lon_max, lat_max)
        return [v for v in all_vessels if v.ais_status == "active"]
