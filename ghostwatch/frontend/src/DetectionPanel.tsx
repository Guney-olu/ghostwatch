import React from "react";
import type { DetectionResult, ScanSummary } from "./ghostwatch-api";

interface DetectionPanelProps {
  detections: DetectionResult[];
  summary: ScanSummary | null;
  scanning: boolean;
  lastScanTime: string | null;
  onSelectDetection: (det: DetectionResult) => void;
  onDispatch: (det: DetectionResult) => void;
  selectedId: string | null;
}

const statusColors: Record<string, string> = {
  ghost: "#ef4444",
  anomalous: "#f59e0b",
  matched: "#10b981",
};

const statusLabels: Record<string, string> = {
  ghost: "GHOST",
  anomalous: "ANOMALOUS",
  matched: "MATCHED",
};

function RiskBar({ score }: { score: number }) {
  const color =
    score >= 80 ? "#ef4444" : score >= 60 ? "#f59e0b" : score >= 30 ? "#3b82f6" : "#10b981";

  return (
    <div className="risk-bar-container">
      <div className="risk-bar-fill" style={{ width: `${score}%`, background: color }} />
      <span className="risk-bar-label">{score}</span>
    </div>
  );
}

export const DetectionPanel: React.FC<DetectionPanelProps> = ({
  detections,
  summary,
  scanning,
  lastScanTime,
  onSelectDetection,
  onDispatch,
  selectedId,
}) => {
  return (
    <div className="detection-panel">
      <h2>Vessel Detections</h2>

      <div className="scan-status">
        {scanning ? (
          <span className="scan-active">
            <span className="scan-dot" /> Scanning...
          </span>
        ) : lastScanTime ? (
          <span className="scan-idle">Last scan: {new Date(lastScanTime).toLocaleTimeString()}</span>
        ) : (
          <span className="scan-idle">No scans yet</span>
        )}
      </div>

      {summary && (
        <div className="scan-summary">
          <div className="summary-stat">
            <span className="summary-value">{summary.total_vessels}</span>
            <span className="summary-label">Total</span>
          </div>
          <div className="summary-stat summary-ghost">
            <span className="summary-value">{summary.ghost_vessels}</span>
            <span className="summary-label">Ghost</span>
          </div>
          <div className="summary-stat summary-matched">
            <span className="summary-value">{summary.matched_vessels}</span>
            <span className="summary-label">Matched</span>
          </div>
        </div>
      )}

      <div className="detection-list">
        {detections.length === 0 && !scanning && (
          <p className="no-detections">No vessels detected</p>
        )}
        {detections.map((det) => (
          <div
            key={det.detection_id}
            className={`detection-card ${selectedId === det.detection_id ? "selected" : ""}`}
            onClick={() => onSelectDetection(det)}
          >
            <div className="detection-header">
              <span
                className="status-badge"
                style={{ background: statusColors[det.ghost_status] }}
              >
                {statusLabels[det.ghost_status]}
              </span>
              <span className="detection-id">{det.detection_id}</span>
            </div>

            <div className="detection-body">
              <div className="detection-info">
                <span className="det-label">{det.estimated_type.replace(/_/g, " ")}</span>
                <span className="det-conf">
                  {(det.confidence * 100).toFixed(0)}% conf
                </span>
              </div>
              <div className="detection-coords">
                {det.coordinates.lat.toFixed(4)}, {det.coordinates.lon.toFixed(4)}
              </div>
              <RiskBar score={det.risk_score} />
            </div>

            {det.ghost_status === "ghost" && (
              <button
                className="dispatch-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onDispatch(det);
                }}
              >
                Dispatch Drone
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
