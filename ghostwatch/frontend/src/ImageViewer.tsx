import React, { useRef, useEffect } from "react";
import type { DetectionResult } from "./ghostwatch-api";

interface ImageViewerProps {
  imageBase64: string | null;
  detections: DetectionResult[];
  selectedId: string | null;
  onSelectDetection: (det: DetectionResult) => void;
}

const statusColors: Record<string, string> = {
  ghost: "#ef4444",
  anomalous: "#f59e0b",
  matched: "#10b981",
};

export const ImageViewer: React.FC<ImageViewerProps> = ({
  imageBase64,
  detections,
  selectedId,
  onSelectDetection,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

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

      // Draw bounding boxes
      detections.forEach((det) => {
        const [x1, y1, x2, y2] = det.bbox;
        const px1 = x1 * img.width;
        const py1 = y1 * img.height;
        const pw = (x2 - x1) * img.width;
        const ph = (y2 - y1) * img.height;

        const color = statusColors[det.ghost_status] || "#ffffff";
        const isSelected = det.detection_id === selectedId;

        // Box
        ctx.strokeStyle = color;
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.strokeRect(px1, py1, pw, ph);

        // Label background
        const label = `${det.estimated_type.replace(/_/g, " ")} ${(det.confidence * 100).toFixed(0)}%`;
        ctx.font = "bold 11px system-ui";
        const metrics = ctx.measureText(label);
        const labelH = 16;
        ctx.fillStyle = color;
        ctx.fillRect(px1, py1 - labelH, metrics.width + 8, labelH);

        // Label text
        ctx.fillStyle = "#ffffff";
        ctx.fillText(label, px1 + 4, py1 - 4);

        // Risk score badge for ghost vessels
        if (det.ghost_status === "ghost") {
          const badge = `RISK ${det.risk_score}`;
          ctx.font = "bold 10px system-ui";
          const badgeW = ctx.measureText(badge).width + 8;
          ctx.fillStyle = "rgba(239, 68, 68, 0.85)";
          ctx.fillRect(px1 + pw - badgeW, py1, badgeW, 14);
          ctx.fillStyle = "#ffffff";
          ctx.fillText(badge, px1 + pw - badgeW + 4, py1 + 11);
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

    // Find which detection was clicked
    for (const det of detections) {
      const [x1, y1, x2, y2] = det.bbox;
      if (clickX >= x1 && clickX <= x2 && clickY >= y1 && clickY <= y2) {
        onSelectDetection(det);
        return;
      }
    }
  };

  if (!imageBase64) {
    return (
      <div className="image-viewer">
        <h2>Satellite Image</h2>
        <div className="no-image">
          <p>No imagery available</p>
          <p className="no-image-sub">Waiting for scan...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="image-viewer">
      <h2>Satellite Image</h2>
      <div className="image-canvas-container">
        <canvas
          ref={canvasRef}
          className="image-canvas"
          onClick={handleCanvasClick}
        />
      </div>
      <div className="image-legend">
        <span className="legend-item">
          <span className="legend-dot" style={{ background: "#10b981" }} /> Matched
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: "#ef4444" }} /> Ghost
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: "#f59e0b" }} /> Anomalous
        </span>
      </div>
    </div>
  );
};
