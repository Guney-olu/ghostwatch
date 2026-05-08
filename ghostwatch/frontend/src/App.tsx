import React, { useEffect, useState, useCallback, useRef } from "react";
import { TelemetryPoint, fetchRecentTelemetry } from "./api";
import { GlobeView } from "./GlobeView";
import { DetectionPanel } from "./DetectionPanel";
import { FloatingImageViewer } from "./FloatingImageViewer";
import { ScanHistory } from "./ScanHistory";
import { DispatchModal } from "./DispatchModal";
import { DroneFeed } from "./DroneFeed";
import { REGIONS, MonitorRegion } from "./regions";
import { RegionSelector } from "./RegionSelector";
import {
  scanRegion,
  getScanHistory,
  deleteScan,
  clearAllScans,
  ScanResponse,
  DetectionResult,
  Coordinates,
} from "./ghostwatch-api";

const AUTOPILOT_INTERVAL_S = 60;

export const App: React.FC = () => {
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([]);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [lastScanTime, setLastScanTime] = useState<string | null>(null);
  const [selectedDetection, setSelectedDetection] = useState<string | null>(null);
  const [dispatchTarget, setDispatchTarget] = useState<DetectionResult | null>(null);
  const [droneTarget, setDroneTarget] = useState<Coordinates | null>(null);
  const [probeDetection, setProbeDetection] = useState<DetectionResult | null>(null);
  const [activeRegion, setActiveRegion] = useState<MonitorRegion>(REGIONS[0]);
  const [targetLat, setTargetLat] = useState<number>(REGIONS[0].lat);
  const [targetLon, setTargetLon] = useState<number>(REGIONS[0].lon);
  const [autopilot, setAutopilot] = useState(false);
  const [autopilotCountdown, setAutopilotCountdown] = useState(AUTOPILOT_INTERVAL_S);
  const [scanHistory, setScanHistory] = useState<ScanResponse[]>([]);

  const targetLatRef = useRef(targetLat);
  const targetLonRef = useRef(targetLon);
  const activeRegionRef = useRef(activeRegion);
  const scanningRef = useRef(scanning);
  useEffect(() => { targetLatRef.current = targetLat; }, [targetLat]);
  useEffect(() => { targetLonRef.current = targetLon; }, [targetLon]);
  useEffect(() => { activeRegionRef.current = activeRegion; }, [activeRegion]);
  useEffect(() => { scanningRef.current = scanning; }, [scanning]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await fetchRecentTelemetry();
        if (!cancelled) setTelemetry(data);
      } catch { /* silent */ }
    };
    poll();
    const handle = setInterval(poll, 1000);
    return () => { cancelled = true; clearInterval(handle); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const backendHistory = await getScanHistory();
        if (cancelled || backendHistory.length === 0) return;
        setScanHistory(backendHistory.slice(0, 200));
        const latest = backendHistory[0];
        setScanResult(latest);
        setLastScanTime(latest.timestamp);
        if (latest.region?.center) {
          setTargetLat(latest.region.center.lat);
          setTargetLon(latest.region.center.lon);
        }
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const runScan = useCallback(async () => {
    if (scanningRef.current) return;
    setScanning(true);
    setDroneTarget(null);
    setProbeDetection(null);
    try {
      const lat = targetLatRef.current;
      const lon = targetLonRef.current;
      const region = activeRegionRef.current;
      const result = await scanRegion(lon, lat, region.timestamp, region.size_km);
      setScanResult(result);
      setLastScanTime(result.timestamp);
      setScanHistory((prev) => [result, ...prev].slice(0, 200));
    } catch (err) {
      console.error("GhostWatch scan failed", err);
    } finally {
      setScanning(false);
    }
  }, []);

  useEffect(() => {
    if (!autopilot) {
      setAutopilotCountdown(AUTOPILOT_INTERVAL_S);
      return;
    }
    let elapsed = 0;
    const tick = setInterval(() => {
      elapsed += 1;
      const remaining = AUTOPILOT_INTERVAL_S - elapsed;
      if (remaining <= 0) {
        const idx = REGIONS.findIndex((r) => r.id === activeRegionRef.current.id);
        const next = REGIONS[(idx + 1) % REGIONS.length];
        setActiveRegion(next);
        setTargetLat(next.lat);
        setTargetLon(next.lon);
        setScanResult(null);
        runScan();
        elapsed = 0;
        setAutopilotCountdown(AUTOPILOT_INTERVAL_S);
      } else {
        setAutopilotCountdown(remaining);
      }
    }, 1000);

    runScan();

    return () => clearInterval(tick);
  }, [autopilot, runScan]);

  const handleDispatchConfirmed = (det: DetectionResult) => {
    setDroneTarget(det.coordinates);
    setProbeDetection(det);
    setDispatchTarget(null);
  };

  const selectRegion = (region: MonitorRegion) => {
    setActiveRegion(region);
    setTargetLat(region.lat);
    setTargetLon(region.lon);
    setScanResult(null);
    setDroneTarget(null);
    setProbeDetection(null);
  };

  const handleMapClick = (lat: number, lon: number) => {
    if (autopilot || scanning) return;
    setTargetLat(lat);
    setTargetLon(lon);
  };

  const handleDeleteScan = (scanId: string) => {
    setScanHistory((prev) => prev.filter((s) => s.scan_id !== scanId));
    if (scanResult?.scan_id === scanId) {
      setScanResult(null);
      setSelectedDetection(null);
      setProbeDetection(null);
      setDroneTarget(null);
    }
    deleteScan(scanId).catch((err) => console.warn("backend delete failed", err));
  };

  const handleClearAllScans = () => {
    setScanHistory([]);
    setScanResult(null);
    setSelectedDetection(null);
    setProbeDetection(null);
    setDroneTarget(null);
    clearAllScans().catch((err) => console.warn("backend clear failed", err));
  };

  const restoreScan = (scan: ScanResponse) => {
    setScanResult(scan);
    setLastScanTime(scan.timestamp);
    if (scan.region?.center) {
      setTargetLat(scan.region.center.lat);
      setTargetLon(scan.region.center.lon);
    }
    setSelectedDetection(null);
    setDroneTarget(null);
    setProbeDetection(null);
  };

  const detections = scanResult?.detections ?? [];
  const targetCoords: Coordinates = { lat: targetLat, lon: targetLon };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1>
            <span className="header-icon">&#9760;</span>
            GhostWatch
          </h1>
          <span className="header-sub">Maritime Intelligence System</span>
        </div>
        <div className="header-right">
          <button
            className={`autopilot-toggle ${autopilot ? "on" : ""}`}
            onClick={() => setAutopilot((v) => !v)}
            title="Auto-cycle scans through curated regions every 60s"
          >
            <span className="autopilot-dot" />
            <span className="autopilot-label">AUTOPILOT</span>
            {autopilot && (
              <span className="autopilot-countdown">{autopilotCountdown}s</span>
            )}
          </button>
          <div className="header-stat">
            <span className="header-stat-value">{detections.length}</span>
            <span className="header-stat-label">Detections</span>
          </div>
          <div className="header-stat header-stat-alert">
            <span className="header-stat-value">
              {detections.filter(d => d.ghost_status === "ghost").length}
            </span>
            <span className="header-stat-label">Threats</span>
          </div>
          <button className="scan-btn" onClick={runScan} disabled={scanning}>
            {scanning ? "Scanning..." : "Scan Now"}
          </button>
        </div>
      </header>
      <main className="app-main">
        <section className="globe-section">
          <RegionSelector active={activeRegion} onSelect={selectRegion} />
          <GlobeView
            telemetry={telemetry}
            detections={detections}
            scanCenter={targetCoords}
            scanId={scanResult?.scan_id ?? null}
            scanSizeKm={scanResult?.region?.size_km ?? activeRegion.size_km}
            droneTarget={droneTarget}
            onMapClick={handleMapClick}
          />
          {probeDetection && scanResult?.image_base64 && (
            <DroneFeed
              imageBase64={scanResult.image_base64}
              detection={probeDetection}
              onClose={() => { setProbeDetection(null); setDroneTarget(null); }}
            />
          )}
          <FloatingImageViewer
            imageBase64={scanResult?.image_base64 ?? null}
            detections={detections}
            selectedId={selectedDetection}
            onSelectDetection={(det) => setSelectedDetection(det.detection_id)}
            scanId={scanResult?.scan_id ?? null}
            scanning={scanning}
          />
          <div className="globe-info-bar">
            <span className="globe-info-region">
              {activeRegion.flag} {activeRegion.name}
            </span>
            <span className="globe-info-coords">
              {targetLat.toFixed(2)}°{targetLat >= 0 ? "N" : "S"}, {targetLon.toFixed(2)}°{targetLon >= 0 ? "E" : "W"}
            </span>
            <span className="globe-info-hint">click globe to retarget</span>
            {scanning && <span className="globe-info-scanning">Scanning...</span>}
            {autopilot && !scanning && (
              <span className="globe-info-scanning">Autopilot · next in {autopilotCountdown}s</span>
            )}
          </div>
        </section>
        <section className="side-panel">
          <DetectionPanel
            detections={detections}
            summary={scanResult?.summary ?? null}
            scanning={scanning}
            lastScanTime={lastScanTime}
            onSelectDetection={(det) => setSelectedDetection(det.detection_id)}
            onDispatch={(det) => setDispatchTarget(det)}
            selectedId={selectedDetection}
          />
          <ScanHistory
            history={scanHistory}
            activeScanId={scanResult?.scan_id ?? null}
            onSelect={restoreScan}
            onClear={handleClearAllScans}
            onDelete={handleDeleteScan}
          />
        </section>
      </main>

      {dispatchTarget && (
        <DispatchModal
          detection={dispatchTarget}
          onClose={() => setDispatchTarget(null)}
          onConfirmed={handleDispatchConfirmed}
        />
      )}
    </div>
  );
};
