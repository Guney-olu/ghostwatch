import React, { useEffect, useRef, useState } from "react";
import type { DetectionResult } from "./ghostwatch-api";

interface Props {
  imageBase64: string | null;
  detections: DetectionResult[];
  selectedId: string | null;
  onSelectDetection: (det: DetectionResult) => void;
  scanId?: string | null;
  scanning?: boolean;
}

const statusColors: Record<string, string> = {
  ghost: "#ef4444",
  anomalous: "#f59e0b",
  matched: "#10b981",
};

export const FloatingImageViewer: React.FC<Props> = ({
  imageBase64,
  detections,
  selectedId,
  onSelectDetection,
  scanId,
  scanning,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !imageBase64) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      detections.forEach((det) => {
        const [x1, y1, x2, y2] = det.bbox;
        const px1 = x1 * img.width;
        const py1 = y1 * img.height;
        const pw = (x2 - x1) * img.width;
        const ph = (y2 - y1) * img.height;

        const color = statusColors[det.ghost_status] || "#ffffff";
        const isSelected = det.detection_id === selectedId;

        ctx.strokeStyle = color;
        ctx.lineWidth = isSelected ? 4 : 2.5;
        ctx.strokeRect(px1, py1, pw, ph);

        const corner = Math.min(12, pw / 4, ph / 4);
        ctx.lineWidth = isSelected ? 5 : 3;
        ctx.beginPath();
        ctx.moveTo(px1, py1 + corner); ctx.lineTo(px1, py1); ctx.lineTo(px1 + corner, py1);
        ctx.moveTo(px1 + pw - corner, py1); ctx.lineTo(px1 + pw, py1); ctx.lineTo(px1 + pw, py1 + corner);
        ctx.moveTo(px1 + pw, py1 + ph - corner); ctx.lineTo(px1 + pw, py1 + ph); ctx.lineTo(px1 + pw - corner, py1 + ph);
        ctx.moveTo(px1 + corner, py1 + ph); ctx.lineTo(px1, py1 + ph); ctx.lineTo(px1, py1 + ph - corner);
        ctx.stroke();

        const label = `${det.estimated_type.replace(/_/g, " ")} ${(det.confidence * 100).toFixed(0)}%`;
        ctx.font = "bold 13px ui-monospace, Menlo, monospace";
        const metrics = ctx.measureText(label);
        const labelH = 18;
        ctx.fillStyle = color;
        ctx.fillRect(px1, py1 - labelH, metrics.width + 10, labelH);

        ctx.fillStyle = "#000000";
        ctx.fillText(label, px1 + 5, py1 - 5);

        if (det.ghost_status === "ghost") {
          const badge = `RISK ${det.risk_score}`;
          ctx.font = "bold 12px ui-monospace, Menlo, monospace";
          const badgeW = ctx.measureText(badge).width + 10;
          ctx.fillStyle = "rgba(239, 68, 68, 0.92)";
          ctx.fillRect(px1 + pw - badgeW, py1, badgeW, 16);
          ctx.fillStyle = "#ffffff";
          ctx.fillText(badge, px1 + pw - badgeW + 5, py1 + 13);
        }
      });
    };
    img.src = `data:image/png;base64,${imageBase64}`;
  }, [imageBase64, detections, selectedId]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !imageBase64) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clickX = (e.clientX - rect.left) * scaleX / canvas.width;
    const clickY = (e.clientY - rect.top) * scaleY / canvas.height;
    for (const det of detections) {
      const [x1, y1, x2, y2] = det.bbox;
      if (clickX >= x1 && clickX <= x2 && clickY >= y1 && clickY <= y2) {
        onSelectDetection(det);
        return;
      }
    }
  };

  if (!imageBase64 && !scanning) return null;

  return (
    <div className={`fiv ${collapsed ? "fiv-collapsed" : ""}`}>
      <div className="fiv-header">
        <div className="fiv-title">
          <span className="fiv-title-bar" />
          <span className="fiv-title-label">SATELLITE IMAGE</span>
          {scanId && <span className="fiv-title-id">{scanId}</span>}
        </div>
        <div className="fiv-header-right">
          {scanning && <span className="fiv-scanning"><span className="fiv-scanning-dot" /> SCANNING…</span>}
          {!scanning && imageBase64 && (
            <span className="fiv-detection-count">{detections.length} DETECTION{detections.length === 1 ? "" : "S"}</span>
          )}
          <button
            className="fiv-collapse"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? "Expand" : "Collapse"}
          >
            {collapsed ? "▢" : "—"}
          </button>
        </div>
      </div>

      {!collapsed && (
        <>
          <div className="fiv-canvas-wrap">
            {imageBase64 ? (
              <canvas
                ref={canvasRef}
                className="fiv-canvas"
                onClick={handleCanvasClick}
              />
            ) : (
              <div className="fiv-placeholder">
                <span className="fiv-placeholder-spinner" />
                <span>Acquiring imagery…</span>
              </div>
            )}
          </div>
          <div className="fiv-legend">
            <span className="fiv-legend-item">
              <span className="fiv-legend-dot" style={{ background: "#10b981" }} /> Matched
            </span>
            <span className="fiv-legend-item">
              <span className="fiv-legend-dot" style={{ background: "#ef4444" }} /> Ghost
            </span>
            <span className="fiv-legend-item">
              <span className="fiv-legend-dot" style={{ background: "#f59e0b" }} /> Anomalous
            </span>
          </div>
        </>
      )}
    </div>
  );
};
