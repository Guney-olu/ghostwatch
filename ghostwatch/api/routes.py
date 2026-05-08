"""GhostWatch API routes."""

import base64
import itertools
import json
import threading
import uuid
from datetime import datetime, timezone
from io import BytesIO

import requests
from fastapi import APIRouter, HTTPException

from ghostwatch import config
from ghostwatch.api.schemas import (
    ScanRequest,
    ScanResponse,
    ScanSummary,
    DetectionResult,
    Coordinates,
    AISMatch,
    DroneDispatch,
    HealthResponse,
    TelemetryIn,
    TelemetryRecent,
    CommandIn,
    CommandRecord,
    CommandsList,
    CommandPolled,
)
from ghostwatch.detector.vlm_detector import VesselDetector
from ghostwatch.detector.bbox_utils import bbox_to_latlon
from ghostwatch.ais.synthetic_ais import SyntheticAISFeed
from ghostwatch.ais.ghost_logic import GhostAnalyzer
from ghostwatch.dispatch.drone_dispatch import generate_dispatch

router = APIRouter()

detector: VesselDetector | None = None
ais_feed: SyntheticAISFeed | None = None
ghost_analyzer: GhostAnalyzer | None = None

_detection_history: dict[str, DetectionResult] = {}
_scan_history: list[ScanResponse] = []

_ALLOWED_COMMANDS = {
    "start", "pause", "stop", "set_start_time", "set_step_size", "set_replay_speed",
}
_telemetry_lock = threading.Lock()
_telemetry_store: dict[str, dict] = {}
_commands_lock = threading.Lock()
_commands_queue: list[dict] = []
_command_id_seq = itertools.count(1)


def init_services():
    """Initialize detector, AIS feed, and ghost analyzer."""
    global detector, ais_feed, ghost_analyzer
    detector = VesselDetector()
    ais_feed = SyntheticAISFeed()
    ghost_analyzer = GhostAnalyzer()


def _image_quality_ok(image_bytes: bytes) -> tuple[bool, str]:
    """Reject Sentinel images that are mostly cloud, mostly dark, or featureless.

    Without this guard the fine-tuned VLM hallucinates "boat 90%" labels on
    pure-cloud or pure-water tiles, producing false positives in the demo.
    Returns (ok, reason). Reason is "" when ok.
    """
    try:
        from PIL import Image as PILImage
        import statistics
        img = PILImage.open(BytesIO(image_bytes)).convert("L").resize((64, 64))
        pixels = list(img.getdata())
        mean = sum(pixels) / len(pixels)
        variance = statistics.pvariance(pixels)
        stddev = variance ** 0.5
        cloud_frac = sum(1 for p in pixels if p > 235) / len(pixels)
        dark_frac = sum(1 for p in pixels if p < 20) / len(pixels)
        if mean < 18:
            return False, f"image too dark (mean brightness {mean:.0f})"
        if cloud_frac > 0.7:
            return False, f"heavy cloud cover ({cloud_frac * 100:.0f}% white)"
        if dark_frac > 0.85:
            return False, f"image mostly black ({dark_frac * 100:.0f}% dark)"
        if stddev < 8:
            return False, f"no contrast (stddev {stddev:.1f})"
        return True, ""
    except Exception as e:
        return True, f"quality check failed: {e}"


@router.post("/api/scan", response_model=ScanResponse)
async def scan_region(req: ScanRequest):
    """Scan a region for vessels. Fetches imagery from SimSat, runs detection,
    compares against AIS, and returns classified results."""
    if not detector or not detector.is_ready:
        raise HTTPException(status_code=503, detail="Detector not ready")

    scan_id = f"GW-{uuid.uuid4().hex[:6].upper()}"

    if config.MOCK_MODE:
        image_bytes, metadata = _generate_mock_image(req.lon, req.lat, req.size_km)
        image_available = True
    else:
        image_bytes, metadata = _fetch_sentinel_image(req.lon, req.lat, req.timestamp, req.size_km)
        image_available = metadata.get("image_available", False) and image_bytes is not None

    quality_reason = ""
    if image_available and image_bytes and not config.MOCK_MODE:
        ok, quality_reason = _image_quality_ok(image_bytes)
        if not ok:
            image_available = False
            metadata["image_unusable_reason"] = quality_reason
            image_bytes = None

    image_b64 = None
    detections_out: list[DetectionResult] = []

    if image_available and image_bytes:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        raw_detections = detector.detect_from_bytes(image_bytes)

        footprint = metadata.get("footprint", [req.lon - 0.025, req.lat - 0.025, req.lon + 0.025, req.lat + 0.025])
        detection_coords = [bbox_to_latlon(d.bbox, footprint) for d in raw_detections]

        ais_vessels = ais_feed.get_vessels_in_region(
            footprint[0], footprint[1], footprint[2], footprint[3]
        )

        ghost_results = ghost_analyzer.analyze(
            raw_detections, detection_coords, ais_vessels, scan_id
        )

        for gd in ghost_results:
            det_result = DetectionResult(
                detection_id=gd.detection_id,
                label=gd.label,
                confidence=gd.confidence,
                bbox=gd.bbox,
                coordinates=Coordinates(lat=gd.lat, lon=gd.lon),
                estimated_type=gd.estimated_type,
                ghost_status=gd.ghost_status,
                risk_score=gd.risk_score,
                reason=gd.reason,
                ais_match=AISMatch(**gd.ais_match) if gd.ais_match else None,
            )
            detections_out.append(det_result)
            _detection_history[gd.detection_id] = det_result

    ghost_count = sum(1 for d in detections_out if d.ghost_status == "ghost")
    matched_count = sum(1 for d in detections_out if d.ghost_status == "matched")

    response = ScanResponse(
        scan_id=scan_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        region={
            "center": {"lat": req.lat, "lon": req.lon},
            "size_km": req.size_km,
            "footprint": metadata.get("footprint"),
        },
        image_available=image_available,
        image_base64=image_b64,
        detections=detections_out,
        summary=ScanSummary(
            total_vessels=len(detections_out),
            ghost_vessels=ghost_count,
            matched_vessels=matched_count,
            dispatches_recommended=ghost_count,
            highest_risk_score=max((d.risk_score for d in detections_out), default=0),
        ),
    )

    _scan_history.append(response)
    if len(_scan_history) > 500:
        _scan_history.pop(0)

    return response


@router.post("/api/scan/current", response_model=ScanResponse)
async def scan_current_position():
    """Scan at the satellite's current position."""
    try:
        resp = requests.get(f"{config.SIMSAT_API_URL}/data/current/position", timeout=10)
        resp.raise_for_status()
        pos_data = resp.json()
        lon_lat_alt = pos_data.get("lon-lat-alt", [0, 0, 0])
        timestamp = pos_data.get("timestamp", datetime.now(timezone.utc).isoformat())
    except Exception as e:
        if config.MOCK_MODE:
            lon_lat_alt = [103.82, 1.25, 550.0]
            timestamp = datetime.now(timezone.utc).isoformat()
        else:
            raise HTTPException(status_code=502, detail=f"Failed to get satellite position: {e}")

    req = ScanRequest(
        lon=lon_lat_alt[0],
        lat=lon_lat_alt[1],
        timestamp=timestamp,
        size_km=config.DEFAULT_SIZE_KM,
    )
    return await scan_region(req)


@router.get("/api/detections")
async def get_detections():
    """Return recent detection history."""
    return {
        "detections": list(_detection_history.values()),
        "total": len(_detection_history),
    }


@router.delete("/api/scans/{scan_id}", status_code=204)
async def delete_scan(scan_id: str):
    """Remove a single scan (and its detections) from in-memory history."""
    global _scan_history
    before = len(_scan_history)
    _scan_history[:] = [s for s in _scan_history if s.scan_id != scan_id]
    if len(_scan_history) == before:
        raise HTTPException(status_code=404, detail="scan not found")
    for det_id in list(_detection_history.keys()):
        if det_id.startswith(scan_id):
            _detection_history.pop(det_id, None)
    return


@router.delete("/api/scans", status_code=204)
async def clear_scan_history():
    """Clear all scan + detection history."""
    _scan_history.clear()
    _detection_history.clear()
    return


@router.get("/api/scans")
async def get_scan_history(include_empty: bool = False):
    """Return the recent scan history (most-recent first).

    By default, scans where Sentinel returned no usable image are hidden
    so the dashboard's history stays clean. Pass ?include_empty=true to
    debug failed retrievals.
    """
    items = list(reversed(_scan_history))
    if not include_empty:
        items = [s for s in items if s.image_available]
    return {"scans": items, "total": len(items)}


@router.get("/api/detections/{detection_id}")
async def get_detection(detection_id: str):
    """Get a single detection by ID."""
    det = _detection_history.get(detection_id)
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")
    return det


@router.post("/api/dispatch/{detection_id}", response_model=DroneDispatch)
async def create_dispatch(detection_id: str):
    """Generate a drone dispatch mission for a detection."""
    det = _detection_history.get(detection_id)
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")

    if det.ghost_status == "matched":
        raise HTTPException(status_code=400, detail="Cannot dispatch to a matched (non-suspicious) vessel")

    from ghostwatch.ais.ghost_logic import GhostDetection
    ghost_det = GhostDetection(
        detection_id=det.detection_id,
        label=det.label,
        confidence=det.confidence,
        bbox=det.bbox,
        lat=det.coordinates.lat,
        lon=det.coordinates.lon,
        ghost_status=det.ghost_status,
        risk_score=det.risk_score,
        reason=det.reason,
        estimated_type=det.estimated_type,
        ais_match=det.ais_match.model_dump() if det.ais_match else None,
    )

    return generate_dispatch(ghost_det)


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check returning model status and connectivity."""
    return HealthResponse(
        status="ok" if detector and detector.is_ready else "loading",
        model_loaded=detector.is_ready if detector else False,
        mock_mode=config.MOCK_MODE,
        simsat_url=config.SIMSAT_API_URL,
    )


def _fetch_sentinel_image(
    lon: float, lat: float, timestamp: str, size_km: float
) -> tuple[bytes | None, dict]:
    """Fetch a Sentinel-2 image from the SimSat API.

    Returns:
        (image_bytes, metadata_dict)
    """
    try:
        resp = requests.get(
            f"{config.SIMSAT_API_URL}/data/image/sentinel",
            params={
                "lon": lon,
                "lat": lat,
                "timestamp": timestamp,
                "return_type": "png",
                "size_km": size_km,
            },
            timeout=60,
        )
        resp.raise_for_status()

        meta_str = resp.headers.get("sentinel_metadata", "{}")
        metadata = json.loads(meta_str)

        if metadata.get("image_available", False):
            return resp.content, metadata
        else:
            return None, metadata

    except Exception as e:
        print(f"[GhostWatch] Error fetching Sentinel image: {e}")
        return None, {"image_available": False, "error": str(e)}


def _generate_mock_image(lon: float, lat: float, size_km: float) -> tuple[bytes, dict]:
    """Generate a placeholder ocean image for mock mode when SimSat is unavailable."""
    from PIL import Image as PILImage, ImageDraw
    import random

    rng = random.Random(int(lon * 100) + int(lat * 100))
    img = PILImage.new("RGB", (512, 512))
    draw = ImageDraw.Draw(img)

    for y in range(512):
        for x in range(0, 512, 4):
            r = rng.randint(15, 30)
            g = rng.randint(30, 55)
            b = rng.randint(60, 100)
            draw.rectangle([x, y, x + 3, y], fill=(r, g, b))

    for _ in range(rng.randint(2, 5)):
        vx = rng.randint(30, 480)
        vy = rng.randint(30, 480)
        vw = rng.randint(4, 12)
        vh = rng.randint(2, 6)
        brightness = rng.randint(180, 240)
        draw.rectangle([vx, vy, vx + vw, vy + vh], fill=(brightness, brightness, brightness - 20))

    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    half_deg = (size_km / 111.0) / 2
    footprint = [lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg]

    metadata = {
        "image_available": True,
        "source": "mock",
        "footprint": footprint,
        "size_km": size_km,
        "cloud_cover": 0,
        "datetime": datetime.now(timezone.utc).isoformat(),
    }

    return image_bytes, metadata


def _parse_iso(s: str) -> str:
    """Validate an ISO-8601 timestamp string and return a normalized form."""
    try:
        s_clean = s.rstrip("Z")
        dt = datetime.fromisoformat(s_clean)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid ISO-8601 timestamp")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.post("/api/telemetry/", status_code=201)
async def telemetry_ingest(payload: TelemetryIn):
    """Sim posts the satellite's current ground position here."""
    timestamp = _parse_iso(payload.timestamp)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "satellite": payload.satellite,
        "timestamp": timestamp,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "altitude": payload.altitude,
        "extra": payload.extra,
        "updated_at": now,
    }
    with _telemetry_lock:
        _telemetry_store[payload.satellite] = record
    return {
        "id": payload.satellite,
        "satellite": payload.satellite,
        "timestamp": timestamp,
        "updated_at": now,
    }


@router.get("/api/telemetry/recent/", response_model=TelemetryRecent)
async def telemetry_recent():
    """Frontend polls this for the latest known position of every satellite."""
    with _telemetry_lock:
        snapshot = list(_telemetry_store.values())
    return {
        "telemetry": [
            {
                "satellite": r["satellite"],
                "timestamp": r["timestamp"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "altitude": r["altitude"],
                "extra": r["extra"],
            }
            for r in snapshot
        ]
    }


@router.get("/api/commands/", response_model=CommandsList)
async def commands_poll():
    """Sim polls this; we drain all unconsumed commands in one shot."""
    with _commands_lock:
        drained = _commands_queue[:]
        _commands_queue.clear()
    return {
        "commands": [
            CommandPolled(command=c["command_type"], parameters=c["parameters"])
            for c in drained
        ]
    }


@router.post("/api/commands/", response_model=CommandRecord, status_code=201)
async def commands_create(payload: CommandIn):
    """Frontend (SimulationControls) posts simulator commands here."""
    cmd = payload.command
    if cmd not in _ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail=f"Invalid command '{cmd}'")

    parameters: dict = {}
    if payload.start_time is not None:
        parameters["start_time"] = _parse_iso(payload.start_time)
    if payload.step_size_seconds is not None:
        if payload.step_size_seconds <= 0:
            raise HTTPException(status_code=400, detail="'step_size_seconds' must be a positive integer")
        parameters["step_size_seconds"] = payload.step_size_seconds
    if payload.replay_speed is not None:
        if payload.replay_speed <= 0:
            raise HTTPException(status_code=400, detail="'replay_speed' must be a positive number")
        parameters["replay_speed"] = payload.replay_speed

    record = {
        "id": next(_command_id_seq),
        "command_type": cmd,
        "parameters": parameters,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _commands_lock:
        _commands_queue.append(record)

    return CommandRecord(
        id=record["id"],
        command=cmd,
        parameters=parameters,
        created_at=record["created_at"],
    )
