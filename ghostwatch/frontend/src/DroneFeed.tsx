import React, { useRef, useEffect, useState } from "react";
import type { DetectionResult } from "./ghostwatch-api";

interface DroneFeedProps {
  imageBase64: string;
  detection: DetectionResult;
  onClose: () => void;
}

type FilterMode = "optical" | "edge" | "thermal" | "contour";

const MODES: { id: FilterMode; label: string; color: string }[] = [
  { id: "optical", label: "OPTICAL", color: "#10b981" },
  { id: "edge", label: "EDGE DETECT", color: "#3b82f6" },
  { id: "thermal", label: "THERMAL", color: "#ef4444" },
  { id: "contour", label: "CONTOUR", color: "#f59e0b" },
];

// Sweep path: drone flies a grid pattern around the detection
function getSweepPoints(cx: number, cy: number, radius: number): { x: number; y: number }[] {
  const pts: { x: number; y: number }[] = [];
  const steps = 24;
  // Spiral outward then circle
  for (let i = 0; i < steps; i++) {
    const t = i / steps;
    const angle = t * Math.PI * 4; // 2 full rotations
    const r = radius * (0.3 + t * 0.7);
    pts.push({
      x: Math.max(0.05, Math.min(0.95, cx + Math.cos(angle) * r)),
      y: Math.max(0.05, Math.min(0.95, cy + Math.sin(angle) * r)),
    });
  }
  return pts;
}

function applyFilter(ctx: CanvasRenderingContext2D, w: number, h: number, mode: FilterMode) {
  if (mode === "optical") return;

  const imageData = ctx.getImageData(0, 0, w, h);
  const src = imageData.data;
  const out = ctx.createImageData(w, h);
  const dst = out.data;

  if (mode === "edge") {
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const i = (y * w + x) * 4;
        const tl = src[((y-1)*w+(x-1))*4], t = src[((y-1)*w+x)*4], tr = src[((y-1)*w+(x+1))*4];
        const l = src[(y*w+(x-1))*4], r = src[(y*w+(x+1))*4];
        const bl = src[((y+1)*w+(x-1))*4], b = src[((y+1)*w+x)*4], br = src[((y+1)*w+(x+1))*4];
        const gx = -tl - 2*l - bl + tr + 2*r + br;
        const gy = -tl - 2*t - tr + bl + 2*b + br;
        const mag = Math.min(255, Math.sqrt(gx*gx + gy*gy));
        dst[i] = 0; dst[i+1] = Math.floor(mag); dst[i+2] = Math.floor(mag*0.4); dst[i+3] = 255;
      }
    }
    ctx.putImageData(out, 0, 0);
  } else if (mode === "thermal") {
    for (let i = 0; i < src.length; i += 4) {
      const gray = src[i]*0.3 + src[i+1]*0.59 + src[i+2]*0.11;
      const t = gray / 255;
      if (t < 0.25) { dst[i]=0; dst[i+1]=0; dst[i+2]=Math.floor(t*4*200); }
      else if (t < 0.5) { const s=(t-0.25)*4; dst[i]=Math.floor(s*200); dst[i+1]=0; dst[i+2]=200; }
      else if (t < 0.75) { const s=(t-0.5)*4; dst[i]=255; dst[i+1]=Math.floor(s*200); dst[i+2]=Math.floor(200-s*200); }
      else { const s=(t-0.75)*4; dst[i]=255; dst[i+1]=200+Math.floor(s*55); dst[i+2]=Math.floor(s*255); }
      dst[i+3] = 255;
    }
    ctx.putImageData(out, 0, 0);
  } else if (mode === "contour") {
    const levels = 8;
    for (let i = 0; i < src.length; i += 4) {
      const gray = src[i]*0.3 + src[i+1]*0.59 + src[i+2]*0.11;
      const q = Math.floor(gray / (256/levels)) * (256/levels);
      const t = q/255;
      if (t < 0.33) { dst[i]=0; dst[i+1]=Math.floor(t*3*220); dst[i+2]=Math.floor(180-t*3*100); }
      else if (t < 0.66) { const s=(t-0.33)*3; dst[i]=Math.floor(s*255); dst[i+1]=Math.floor(220-s*70); dst[i+2]=0; }
      else { const s=(t-0.66)*3; dst[i]=255; dst[i+1]=Math.floor(150-s*150); dst[i+2]=0; }
      dst[i+3] = 255;
    }
    ctx.putImageData(out, 0, 0);
  }
}

export const DroneFeed: React.FC<DroneFeedProps> = ({ imageBase64, detection, onClose }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const frameRef = useRef(0);
  const [mode, setMode] = useState<FilterMode>("optical");
  const [sweepIdx, setSweepIdx] = useState(0);
  const [status, setStatus] = useState("INITIALIZING...");

  const cx = (detection.bbox[0] + detection.bbox[2]) / 2;
  const cy = (detection.bbox[1] + detection.bbox[3]) / 2;
  const sweepPoints = useRef(getSweepPoints(cx, cy, 0.2));

  // Load source image once
  useEffect(() => {
    const img = new Image();
    img.onload = () => { imgRef.current = img; };
    img.src = `data:image/png;base64,${imageBase64}`;
  }, [imageBase64]);

  // Animation loop
  useEffect(() => {
    const statuses = [
      "ACQUIRING TARGET...", "SCANNING SECTOR...", "ANALYZING ANOMALY...",
      "TRACKING VESSEL...", "COLLECTING DATA...", "SWEEP IN PROGRESS...",
    ];

    const interval = setInterval(() => {
      setSweepIdx((prev) => {
        const next = (prev + 1) % sweepPoints.current.length;
        if (next === 0) {
          // Cycle filter mode each full sweep
          setMode((m) => {
            const idx = MODES.findIndex((md) => md.id === m);
            return MODES[(idx + 1) % MODES.length].id;
          });
        }
        return next;
      });
      setStatus(statuses[Math.floor(Math.random() * statuses.length)]);
    }, 400);

    return () => clearInterval(interval);
  }, []);

  // Render frame
  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const size = 400;
    canvas.width = size;
    canvas.height = size;

    const pt = sweepPoints.current[sweepIdx];
    const viewSize = 0.18; // crop window size (normalized)

    const sx = Math.max(0, pt.x - viewSize / 2) * img.width;
    const sy = Math.max(0, pt.y - viewSize / 2) * img.height;
    const sw = viewSize * img.width;
    const sh = viewSize * img.height;

    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, size, size);

    // Apply current filter
    applyFilter(ctx, size, size, mode);

    // Draw HUD overlay
    drawHUD(ctx, size, detection, mode, sweepIdx, sweepPoints.current.length);

    frameRef.current++;
  }, [sweepIdx, mode, detection]);

  const currentMode = MODES.find((m) => m.id === mode)!;

  return (
    <div className="drone-feed-panel">
      <div className="drone-feed-header">
        <div className="drone-feed-title">
          <span className="drone-feed-dot" /> DRONE LIVE FEED
        </div>
        <button className="drone-feed-close" onClick={onClose}>&times;</button>
      </div>
      <div className="drone-feed-canvas-wrap">
        <canvas ref={canvasRef} className="drone-feed-canvas" />
      </div>
      <div className="drone-feed-bar">
        <span className="drone-feed-status">{status}</span>
        <span className="drone-feed-mode" style={{ color: currentMode.color }}>
          {currentMode.label}
        </span>
      </div>
      <div className="drone-feed-modes">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={`drone-mode-btn ${mode === m.id ? "active" : ""}`}
            style={{ borderColor: mode === m.id ? m.color : "transparent" }}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
};

function drawHUD(
  ctx: CanvasRenderingContext2D,
  size: number,
  det: DetectionResult,
  mode: FilterMode,
  idx: number,
  total: number,
) {
  const color = mode === "optical" ? "#10b981" : mode === "edge" ? "#3b82f6" : mode === "thermal" ? "#ef4444" : "#f59e0b";

  // Crosshair center
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.6;
  const cx = size / 2, cy = size / 2;
  ctx.beginPath();
  ctx.moveTo(cx - 30, cy); ctx.lineTo(cx - 8, cy);
  ctx.moveTo(cx + 8, cy); ctx.lineTo(cx + 30, cy);
  ctx.moveTo(cx, cy - 30); ctx.lineTo(cx, cy - 8);
  ctx.moveTo(cx, cy + 8); ctx.lineTo(cx, cy + 30);
  ctx.stroke();
  ctx.beginPath(); ctx.arc(cx, cy, 25, 0, Math.PI * 2); ctx.stroke();
  ctx.globalAlpha = 1;

  // Corner brackets
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  const m = 8, l = 25;
  // top-left
  ctx.beginPath(); ctx.moveTo(m, m + l); ctx.lineTo(m, m); ctx.lineTo(m + l, m); ctx.stroke();
  // top-right
  ctx.beginPath(); ctx.moveTo(size - m - l, m); ctx.lineTo(size - m, m); ctx.lineTo(size - m, m + l); ctx.stroke();
  // bottom-left
  ctx.beginPath(); ctx.moveTo(m, size - m - l); ctx.lineTo(m, size - m); ctx.lineTo(m + l, size - m); ctx.stroke();
  // bottom-right
  ctx.beginPath(); ctx.moveTo(size - m - l, size - m); ctx.lineTo(size - m, size - m); ctx.lineTo(size - m, size - m - l); ctx.stroke();

  // Top bar — coordinates
  ctx.fillStyle = "rgba(0,0,0,0.5)";
  ctx.fillRect(0, 0, size, 22);
  ctx.font = "bold 10px monospace";
  ctx.fillStyle = color;
  ctx.fillText(`LAT ${det.coordinates.lat.toFixed(4)}  LON ${det.coordinates.lon.toFixed(4)}`, 8, 14);
  ctx.fillText(`ALT 500m`, size - 70, 14);

  // Bottom bar — sweep progress
  ctx.fillStyle = "rgba(0,0,0,0.5)";
  ctx.fillRect(0, size - 22, size, 22);
  ctx.fillStyle = color;
  const progress = idx / total;
  ctx.fillRect(8, size - 14, (size - 16) * progress, 6);
  ctx.strokeStyle = "rgba(255,255,255,0.3)";
  ctx.strokeRect(8, size - 14, size - 16, 6);

  // Risk badge
  if (det.ghost_status === "ghost") {
    ctx.fillStyle = "rgba(239, 68, 68, 0.85)";
    ctx.fillRect(size - 80, 28, 72, 20);
    ctx.fillStyle = "#fff";
    ctx.font = "bold 10px system-ui";
    ctx.fillText(`RISK ${det.risk_score}`, size - 74, 42);
  }
}
