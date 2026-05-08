import axios from "axios";

// GhostWatch backend - in Docker it's at port 9010, in dev adjust as needed
const gw = axios.create({
  baseURL: window.location.port === "5173"
    ? "http://localhost:9010"  // Vite dev server -> local ghostwatch
    : `${window.location.protocol}//${window.location.hostname}:9010`,
  timeout: 120000, // 2 min — CPU inference + Sentinel fetch can be slow
});

export interface Coordinates {
  lat: number;
  lon: number;
}

export interface AISMatch {
  mmsi: string;
  vessel_name: string;
  vessel_type: string;
  distance_km: number;
}

export interface DetectionResult {
  detection_id: string;
  label: string;
  confidence: number;
  bbox: number[];
  coordinates: Coordinates;
  estimated_type: string;
  ghost_status: "matched" | "ghost" | "anomalous";
  risk_score: number;
  reason: string;
  ais_match: AISMatch | null;
}

export interface ScanSummary {
  total_vessels: number;
  ghost_vessels: number;
  matched_vessels: number;
  dispatches_recommended: number;
  highest_risk_score: number;
}

export interface ScanResponse {
  scan_id: string;
  timestamp: string;
  region: {
    center: Coordinates;
    size_km: number;
    footprint: number[] | null;
  };
  image_available: boolean;
  image_base64: string | null;
  detections: DetectionResult[];
  summary: ScanSummary;
}

export interface MissionPayload {
  waypoints: { lat: number; lon: number; altitude_m: number; action: string }[];
  camera_settings: Record<string, unknown>;
  communication: Record<string, unknown>;
  rules_of_engagement: string;
}

export interface DroneDispatch {
  dispatch_id: string;
  target: DetectionResult;
  priority: "critical" | "high" | "medium" | "low";
  drone_action: string;
  scan_radius_km: number;
  mission_payload: MissionPayload;
}

export async function scanCurrent(): Promise<ScanResponse> {
  const res = await gw.post<ScanResponse>("/api/scan/current");
  return res.data;
}

export async function scanRegion(
  lon: number,
  lat: number,
  timestamp: string,
  size_km = 5.0,
): Promise<ScanResponse> {
  const res = await gw.post<ScanResponse>("/api/scan", {
    lon,
    lat,
    timestamp,
    size_km,
  });
  return res.data;
}

export async function getScanHistory(): Promise<ScanResponse[]> {
  const res = await gw.get<{ scans: ScanResponse[]; total: number }>("/api/scans");
  return res.data.scans ?? [];
}

export async function deleteScan(scanId: string): Promise<void> {
  await gw.delete(`/api/scans/${scanId}`);
}

export async function clearAllScans(): Promise<void> {
  await gw.delete("/api/scans");
}

export async function getDetections(): Promise<{
  detections: DetectionResult[];
  total: number;
}> {
  const res = await gw.get("/api/detections");
  return res.data;
}

export async function generateDispatch(
  detectionId: string,
): Promise<DroneDispatch> {
  const res = await gw.post<DroneDispatch>(`/api/dispatch/${detectionId}`);
  return res.data;
}

export async function healthCheck(): Promise<{
  status: string;
  model_loaded: boolean;
  mock_mode: boolean;
}> {
  const res = await gw.get("/api/health");
  return res.data;
}
