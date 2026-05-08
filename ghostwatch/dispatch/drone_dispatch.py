"""Drone dispatch mission generator.

Converts ghost vessel detections into mission-ready payloads
for autonomous drone investigation.
"""

from ghostwatch.ais.ghost_logic import GhostDetection
from ghostwatch.api.schemas import DroneDispatch, DetectionResult, Coordinates, MissionPayload


def generate_dispatch(detection: GhostDetection) -> DroneDispatch:
    """Generate a drone dispatch mission for a ghost vessel detection.

    Args:
        detection: A classified ghost vessel detection

    Returns:
        DroneDispatch with full mission payload
    """
    priority = _risk_to_priority(detection.risk_score)
    scan_radius = _calculate_scan_radius(detection)

    target = DetectionResult(
        detection_id=detection.detection_id,
        label=detection.label,
        confidence=detection.confidence,
        bbox=detection.bbox,
        coordinates=Coordinates(lat=detection.lat, lon=detection.lon),
        estimated_type=detection.estimated_type,
        ghost_status=detection.ghost_status,
        risk_score=detection.risk_score,
        reason=detection.reason,
        ais_match=None,
    )

    mission = MissionPayload(
        waypoints=[
            {
                "lat": detection.lat,
                "lon": detection.lon,
                "altitude_m": 500,
                "action": "approach",
            },
            {
                "lat": detection.lat,
                "lon": detection.lon,
                "altitude_m": 200,
                "action": "orbit_and_observe",
            },
        ],
        camera_settings={
            "mode": "tracking",
            "zoom": "auto",
            "capture_interval_seconds": 5,
            "ir_enabled": priority in ("critical", "high"),
        },
        communication={
            "report_interval_seconds": 30,
            "live_feed": priority == "critical",
            "alert_on_movement": True,
        },
        rules_of_engagement="observe_and_report",
    )

    return DroneDispatch(
        dispatch_id=f"DSP-{detection.detection_id}",
        target=target,
        priority=priority,
        drone_action="investigate_target",
        scan_radius_km=scan_radius,
        mission_payload=mission,
    )


def _risk_to_priority(risk_score: int) -> str:
    if risk_score >= 85:
        return "critical"
    elif risk_score >= 70:
        return "high"
    elif risk_score >= 50:
        return "medium"
    return "low"


def _calculate_scan_radius(detection: GhostDetection) -> float:
    """Larger scan radius for higher-risk or larger vessels."""
    base = 3.0
    if detection.risk_score >= 85:
        base = 8.0
    elif detection.risk_score >= 70:
        base = 5.0

    if detection.label in ("cargo_ship", "tanker", "container_ship"):
        base += 2.0

    return base
