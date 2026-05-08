import React, { useState } from "react";
import type { DetectionResult, DroneDispatch } from "./ghostwatch-api";
import { generateDispatch } from "./ghostwatch-api";

interface DispatchModalProps {
  detection: DetectionResult;
  onClose: () => void;
  onConfirmed?: (det: DetectionResult) => void;
}

export const DispatchModal: React.FC<DispatchModalProps> = ({
  detection,
  onClose,
  onConfirmed,
}) => {
  const [dispatch, setDispatch] = useState<DroneDispatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await generateDispatch(detection.detection_id);
      setDispatch(result);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to generate dispatch");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = () => {
    setConfirmed(true);
    onConfirmed?.(detection);
  };

  // Auto-generate on mount
  React.useEffect(() => {
    handleGenerate();
  }, []);

  const priorityColors: Record<string, string> = {
    critical: "#ef4444",
    high: "#f59e0b",
    medium: "#3b82f6",
    low: "#10b981",
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Drone Dispatch</h2>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        {loading && <div className="modal-loading">Generating mission...</div>}

        {dispatch && !confirmed && (
          <>
            <div className="dispatch-summary">
              <div className="dispatch-target">
                <span className="dispatch-label">Target</span>
                <span className="dispatch-value">{detection.detection_id}</span>
              </div>
              <div className="dispatch-target">
                <span className="dispatch-label">Priority</span>
                <span
                  className="dispatch-priority"
                  style={{ color: priorityColors[dispatch.priority] }}
                >
                  {dispatch.priority.toUpperCase()}
                </span>
              </div>
              <div className="dispatch-target">
                <span className="dispatch-label">Coordinates</span>
                <span className="dispatch-value">
                  {detection.coordinates.lat.toFixed(4)},{" "}
                  {detection.coordinates.lon.toFixed(4)}
                </span>
              </div>
              <div className="dispatch-target">
                <span className="dispatch-label">Scan Radius</span>
                <span className="dispatch-value">
                  {dispatch.scan_radius_km} km
                </span>
              </div>
            </div>

            <div className="mission-json">
              <h3>Mission Payload</h3>
              <pre>{JSON.stringify(dispatch.mission_payload, null, 2)}</pre>
            </div>

            <button className="confirm-dispatch-btn" onClick={handleConfirm}>
              Confirm Dispatch
            </button>
          </>
        )}

        {confirmed && (
          <div className="dispatch-confirmed">
            <div className="confirmed-icon">&#10003;</div>
            <p>Drone dispatch confirmed</p>
            <p className="confirmed-id">{dispatch?.dispatch_id}</p>
            <p className="confirmed-sub">
              Autonomous investigation en route to target coordinates
            </p>
            <button className="modal-done-btn" onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
