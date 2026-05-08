"""Pydantic models for GhostWatch API request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional


class ScanRequest(BaseModel):
    lon: float = Field(..., ge=-180, le=180, description="Longitude of scan center")
    lat: float = Field(..., ge=-90, le=90, description="Latitude of scan center")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    size_km: float = Field(default=5.0, gt=0, description="Scan area size in km")
    use_demo_scenario: bool = Field(default=False, description="Use pre-defined demo scenario")


class Coordinates(BaseModel):
    lat: float
    lon: float


class AISMatch(BaseModel):
    mmsi: str
    vessel_name: str
    vessel_type: str
    distance_km: float


class DetectionResult(BaseModel):
    detection_id: str
    label: str
    confidence: float
    bbox: list[float]
    coordinates: Coordinates
    estimated_type: str
    ghost_status: str  # "matched", "ghost", "anomalous"
    risk_score: int
    reason: str
    ais_match: Optional[AISMatch] = None


class ScanSummary(BaseModel):
    total_vessels: int
    ghost_vessels: int
    matched_vessels: int
    dispatches_recommended: int
    highest_risk_score: int


class ScanResponse(BaseModel):
    scan_id: str
    timestamp: str
    region: dict
    image_available: bool
    image_base64: Optional[str] = None
    detections: list[DetectionResult]
    summary: ScanSummary


class MissionPayload(BaseModel):
    waypoints: list[dict]
    camera_settings: dict
    communication: dict
    rules_of_engagement: str


class DroneDispatch(BaseModel):
    dispatch_id: str
    target: DetectionResult
    priority: str  # "critical", "high", "medium", "low"
    drone_action: str
    scan_radius_km: float
    mission_payload: MissionPayload


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    mock_mode: bool
    simsat_url: str


class TelemetryIn(BaseModel):
    satellite: str
    timestamp: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    extra: Optional[dict] = None


class TelemetryPoint(BaseModel):
    satellite: str
    timestamp: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    extra: Optional[dict] = None


class TelemetryRecent(BaseModel):
    telemetry: list[TelemetryPoint]


class CommandIn(BaseModel):
    command: str
    start_time: Optional[str] = None
    step_size_seconds: Optional[int] = None
    replay_speed: Optional[float] = None


class CommandRecord(BaseModel):
    id: int
    command: str
    parameters: dict
    created_at: str


class CommandPolled(BaseModel):
    command: str
    parameters: dict


class CommandsList(BaseModel):
    commands: list[CommandPolled]
