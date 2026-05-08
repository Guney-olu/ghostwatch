import React from "react";
import type { ScanResponse } from "./ghostwatch-api";

interface Props {
  history: ScanResponse[];
  activeScanId: string | null;
  onSelect: (scan: ScanResponse) => void;
  onClear: () => void;
  onDelete: (scanId: string) => void;
}

const fmtTime = (iso: string) => {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
};

const fmtCoords = (lat: number, lon: number) =>
  `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"} ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;

export const ScanHistory: React.FC<Props> = ({ history, activeScanId, onSelect, onClear, onDelete }) => {
  return (
    <div className="scan-history">
      <div className="scan-history-header">
        <h2>Scan History {history.length > 0 && <span className="scan-history-count">{history.length}</span>}</h2>
        {history.length > 0 && (
          <button className="scan-history-clear" onClick={onClear} title="Clear all history">CLEAR ALL</button>
        )}
      </div>

      {history.length === 0 ? (
        <div className="scan-history-empty">No scans yet</div>
      ) : (
        <div className="scan-history-list">
          {history.map((scan) => {
            const total = scan.summary?.total_vessels ?? scan.detections.length;
            const ghosts = scan.summary?.ghost_vessels ?? 0;
            const center = scan.region?.center;
            const isActive = scan.scan_id === activeScanId;
            return (
              <div
                key={scan.scan_id}
                className={`scan-history-item ${isActive ? "active" : ""}`}
                onClick={() => onSelect(scan)}
              >
                <div className="scan-history-item-top">
                  <span className="scan-history-item-id">{scan.scan_id}</span>
                  <span className="scan-history-item-time">{fmtTime(scan.timestamp)}</span>
                </div>
                <div className="scan-history-item-coords">
                  {center ? fmtCoords(center.lat, center.lon) : "—"}
                </div>
                <div className="scan-history-item-stats">
                  <span className="scan-history-stat">
                    <span className="scan-history-stat-num">{total}</span>
                    <span className="scan-history-stat-label">det</span>
                  </span>
                  {ghosts > 0 && (
                    <span className="scan-history-stat scan-history-stat-ghost">
                      <span className="scan-history-stat-num">{ghosts}</span>
                      <span className="scan-history-stat-label">ghost</span>
                    </span>
                  )}
                  {!scan.image_available && (
                    <span className="scan-history-stat scan-history-stat-noimg">no image</span>
                  )}
                </div>
                <button
                  className="scan-history-item-delete"
                  title="Remove this scan"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(scan.scan_id);
                  }}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
