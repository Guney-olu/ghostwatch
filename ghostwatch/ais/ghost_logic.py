"""Ghost vessel detection logic.

Compares VLM visual detections against AIS tracking data to identify
vessels that are physically present but not broadcasting their position.
"""

from dataclasses import dataclass, field

from ghostwatch.detector.prompt_templates import Detection
from ghostwatch.detector.bbox_utils import haversine_km
from ghostwatch.ais.synthetic_ais import AISVessel
from ghostwatch import config


@dataclass
class GhostDetection:
    detection_id: str
    label: str
    confidence: float
    bbox: list[float]
    lat: float
    lon: float
    ghost_status: str
    risk_score: int
    reason: str
    estimated_type: str
    ais_match: dict | None = None


_SENSITIVE_ZONES = [
    {"name": "Strait of Malacca", "lat_min": 1.0, "lat_max": 4.0, "lon_min": 99.0, "lon_max": 104.5},
    {"name": "Strait of Hormuz", "lat_min": 25.5, "lat_max": 27.0, "lon_min": 55.5, "lon_max": 57.0},
    {"name": "Gulf of Guinea", "lat_min": 0.0, "lat_max": 6.0, "lon_min": -1.0, "lon_max": 8.0},
    {"name": "South China Sea", "lat_min": 5.0, "lat_max": 22.0, "lon_min": 109.0, "lon_max": 120.0},
    {"name": "Gulf of Aden", "lat_min": 11.0, "lat_max": 15.0, "lon_min": 43.0, "lon_max": 51.0},
]


class GhostAnalyzer:
    """Analyzes vessel detections against AIS data to find ghost ships."""

    def __init__(self, match_radius_km: float | None = None):
        self.match_radius_km = match_radius_km or config.GHOST_MATCH_RADIUS_KM

    def analyze(
        self,
        detections: list[Detection],
        detection_coords: list[tuple[float, float]],
        ais_vessels: list[AISVessel],
        scan_id: str = "GW",
    ) -> list[GhostDetection]:
        """Compare visual detections against AIS vessels.

        Args:
            detections: VLM detection results
            detection_coords: (lat, lon) for each detection
            ais_vessels: AIS vessel data for the same region
            scan_id: Prefix for detection IDs

        Returns:
            List of GhostDetection with classification and risk scoring
        """
        active_ais = [v for v in ais_vessels if v.ais_status != "dark"]

        results = []
        ghost_count = 0

        for i, (det, (lat, lon)) in enumerate(zip(detections, detection_coords)):
            det_id = f"{scan_id}-{i + 1:03d}"

            match, distance = self._find_nearest_ais(lat, lon, active_ais)

            if match and distance <= self.match_radius_km:
                ghost_status = "matched"
                reason = f"AIS match: {match.vessel_name} ({match.mmsi}) at {distance:.2f} km"
                risk_score = self._score_matched(det, match, lat, lon)
                ais_info = {
                    "mmsi": match.mmsi,
                    "vessel_name": match.vessel_name,
                    "vessel_type": match.vessel_type,
                    "distance_km": round(distance, 3),
                }
            else:
                ghost_status = "ghost"
                ghost_count += 1
                reason = "Visual vessel detected but no matching AIS signal found"
                if match:
                    reason += f" (nearest AIS: {match.vessel_name} at {distance:.1f} km)"
                risk_score = self._score_ghost(det, lat, lon, ghost_count)
                ais_info = None

            results.append(GhostDetection(
                detection_id=det_id,
                label=det.label,
                confidence=det.confidence,
                bbox=det.bbox,
                lat=lat,
                lon=lon,
                ghost_status=ghost_status,
                risk_score=risk_score,
                reason=reason,
                estimated_type=det.label,
                ais_match=ais_info,
            ))

        return results

    def _find_nearest_ais(
        self, lat: float, lon: float, ais_vessels: list[AISVessel]
    ) -> tuple[AISVessel | None, float]:
        """Find the nearest AIS vessel to a detection point."""
        if not ais_vessels:
            return None, float("inf")

        nearest = None
        min_dist = float("inf")

        for vessel in ais_vessels:
            dist = haversine_km(lat, lon, vessel.lat, vessel.lon)
            if dist < min_dist:
                min_dist = dist
                nearest = vessel

        return nearest, min_dist

    def _score_ghost(
        self, det: Detection, lat: float, lon: float, ghost_count: int
    ) -> int:
        """Calculate risk score for a ghost vessel (no AIS)."""
        score = 80 + int(det.confidence * 10)

        zone = self._check_sensitive_zone(lat, lon)
        if zone:
            score += 8

        if ghost_count > 1:
            score += min(5 * (ghost_count - 1), 10)

        if det.label in ("cargo_ship", "tanker", "container_ship"):
            score += 5

        return min(score, 100)

    def _score_matched(
        self, det: Detection, ais: AISVessel, lat: float, lon: float
    ) -> int:
        """Calculate risk score for a matched vessel."""
        score = 10

        if det.label != "unknown_vessel" and det.label != ais.vessel_type:
            score += 25

        if ais.ais_status == "intermittent":
            score += 15

        if self._check_sensitive_zone(lat, lon):
            score += 5

        return min(score, 100)

    def _check_sensitive_zone(self, lat: float, lon: float) -> dict | None:
        """Check if coordinates fall in a sensitive maritime zone."""
        for zone in _SENSITIVE_ZONES:
            if (zone["lat_min"] <= lat <= zone["lat_max"] and
                    zone["lon_min"] <= lon <= zone["lon_max"]):
                return zone
        return None
