import React, { useRef, useEffect } from "react";
import type { DetectionResult } from "./ghostwatch-api";

interface AnalysisCardsProps {
  imageBase64: string | null;
  detection: DetectionResult | null;
}

type FilterFn = (ctx: CanvasRenderingContext2D, w: number, h: number) => void;

function applyEdgeDetection(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const imageData = ctx.getImageData(0, 0, w, h);
  const src = imageData.data;
  const out = ctx.createImageData(w, h);
  const dst = out.data;

  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = (y * w + x) * 4;
      // Sobel operator
      const tl = src[((y - 1) * w + (x - 1)) * 4];
      const t  = src[((y - 1) * w + x) * 4];
      const tr = src[((y - 1) * w + (x + 1)) * 4];
      const l  = src[(y * w + (x - 1)) * 4];
      const r  = src[(y * w + (x + 1)) * 4];
      const bl = src[((y + 1) * w + (x - 1)) * 4];
      const b  = src[((y + 1) * w + x) * 4];
      const br = src[((y + 1) * w + (x + 1)) * 4];

      const gx = -tl - 2 * l - bl + tr + 2 * r + br;
      const gy = -tl - 2 * t - tr + bl + 2 * b + br;
      const mag = Math.min(255, Math.sqrt(gx * gx + gy * gy));

      // Green tint for edge detection
      dst[i] = 0;
      dst[i + 1] = Math.floor(mag);
      dst[i + 2] = Math.floor(mag * 0.3);
      dst[i + 3] = 255;
    }
  }
  ctx.putImageData(out, 0, 0);
}

function applyContour(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const imageData = ctx.getImageData(0, 0, w, h);
  const src = imageData.data;
  const out = ctx.createImageData(w, h);
  const dst = out.data;

  // Threshold-based contour with quantized levels
  const levels = 6;
  for (let i = 0; i < src.length; i += 4) {
    const gray = (src[i] * 0.3 + src[i + 1] * 0.59 + src[i + 2] * 0.11);
    const q = Math.floor(gray / (256 / levels)) * (256 / levels);

    // Color map: dark blue -> cyan -> yellow -> red
    const t = q / 255;
    if (t < 0.33) {
      dst[i] = 0;
      dst[i + 1] = Math.floor(t * 3 * 200);
      dst[i + 2] = Math.floor(180 - t * 3 * 100);
    } else if (t < 0.66) {
      const t2 = (t - 0.33) * 3;
      dst[i] = Math.floor(t2 * 255);
      dst[i + 1] = Math.floor(200 - t2 * 50);
      dst[i + 2] = 0;
    } else {
      const t3 = (t - 0.66) * 3;
      dst[i] = 255;
      dst[i + 1] = Math.floor(150 - t3 * 150);
      dst[i + 2] = 0;
    }
    dst[i + 3] = 255;
  }
  ctx.putImageData(out, 0, 0);
}

function applyEnhanced(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const imageData = ctx.getImageData(0, 0, w, h);
  const d = imageData.data;

  // High contrast + false color (NIR-like simulation)
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2];
    // Boost contrast
    d[i] = Math.min(255, Math.floor((r - 80) * 2.5 + 40));     // red channel boost
    d[i + 1] = Math.min(255, Math.floor((g - 60) * 1.8 + 20)); // moderate green
    d[i + 2] = Math.min(255, Math.floor(b * 0.6));               // suppress blue (water)
    d[i + 3] = 255;
  }
  ctx.putImageData(imageData, 0, 0);
}

function applyThermal(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const imageData = ctx.getImageData(0, 0, w, h);
  const src = imageData.data;
  const out = ctx.createImageData(w, h);
  const dst = out.data;

  for (let i = 0; i < src.length; i += 4) {
    const gray = (src[i] * 0.3 + src[i + 1] * 0.59 + src[i + 2] * 0.11);
    const t = gray / 255;

    // Thermal: black -> blue -> magenta -> red -> yellow -> white
    if (t < 0.2) {
      dst[i] = 0; dst[i + 1] = 0; dst[i + 2] = Math.floor(t * 5 * 180);
    } else if (t < 0.4) {
      const s = (t - 0.2) * 5;
      dst[i] = Math.floor(s * 200); dst[i + 1] = 0; dst[i + 2] = 180;
    } else if (t < 0.6) {
      const s = (t - 0.4) * 5;
      dst[i] = 200 + Math.floor(s * 55); dst[i + 1] = 0; dst[i + 2] = Math.floor(180 - s * 180);
    } else if (t < 0.8) {
      const s = (t - 0.6) * 5;
      dst[i] = 255; dst[i + 1] = Math.floor(s * 255); dst[i + 2] = 0;
    } else {
      const s = (t - 0.8) * 5;
      dst[i] = 255; dst[i + 1] = 255; dst[i + 2] = Math.floor(s * 255);
    }
    dst[i + 3] = 255;
  }
  ctx.putImageData(out, 0, 0);
}

interface CardDef {
  title: string;
  subtitle: string;
  filter: FilterFn | null; // null = original
}

const cards: CardDef[] = [
  { title: "OPTICAL", subtitle: "Raw satellite imagery", filter: null },
  { title: "EDGE DETECT", subtitle: "Sobel gradient analysis", filter: applyEdgeDetection },
  { title: "THERMAL SIM", subtitle: "Simulated thermal view", filter: applyThermal },
  { title: "CONTOUR MAP", subtitle: "Quantized elevation bands", filter: applyContour },
];

function AnalysisCard({
  imageBase64,
  detection,
  card,
}: {
  imageBase64: string;
  detection: DetectionResult | null;
  card: CardDef;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Crop to detection area if available, otherwise show full image
      let sx = 0, sy = 0, sw = img.width, sh = img.height;

      if (detection) {
        const [x1, y1, x2, y2] = detection.bbox;
        // Expand crop area around detection for context
        const pad = 0.15;
        const cx = (x1 + x2) / 2;
        const cy = (y1 + y2) / 2;
        const halfW = Math.max((x2 - x1) / 2 + pad, 0.15);
        const halfH = Math.max((y2 - y1) / 2 + pad, 0.15);

        sx = Math.max(0, (cx - halfW)) * img.width;
        sy = Math.max(0, (cy - halfH)) * img.height;
        sw = Math.min(1, halfW * 2) * img.width;
        sh = Math.min(1, halfH * 2) * img.height;
      }

      const size = 200;
      canvas.width = size;
      canvas.height = size;
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, size, size);

      // Apply filter
      if (card.filter) {
        card.filter(ctx, size, size);
      }

      // Draw crosshair on detection center
      if (detection) {
        ctx.strokeStyle = card.filter ? "#00ff00" : "#ef4444";
        ctx.lineWidth = 1.5;
        const cx = size / 2;
        const cy = size / 2;
        // Crosshair
        ctx.beginPath();
        ctx.moveTo(cx - 15, cy); ctx.lineTo(cx - 5, cy);
        ctx.moveTo(cx + 5, cy); ctx.lineTo(cx + 15, cy);
        ctx.moveTo(cx, cy - 15); ctx.lineTo(cx, cy - 5);
        ctx.moveTo(cx, cy + 5); ctx.lineTo(cx, cy + 15);
        ctx.stroke();
        // Circle
        ctx.beginPath();
        ctx.arc(cx, cy, 20, 0, Math.PI * 2);
        ctx.stroke();
      }
    };
    img.src = `data:image/png;base64,${imageBase64}`;
  }, [imageBase64, detection, card]);

  return (
    <div className="analysis-card">
      <canvas ref={canvasRef} className="analysis-canvas" />
      <div className="analysis-label">
        <span className="analysis-title">{card.title}</span>
        <span className="analysis-sub">{card.subtitle}</span>
      </div>
    </div>
  );
}

export const AnalysisCards: React.FC<AnalysisCardsProps> = ({
  imageBase64,
  detection,
}) => {
  if (!imageBase64) return null;

  return (
    <div className="analysis-panel">
      <h2>Drone Probe Analysis</h2>
      <div className="analysis-grid">
        {cards.map((card) => (
          <AnalysisCard
            key={card.title}
            imageBase64={imageBase64}
            detection={detection}
            card={card}
          />
        ))}
      </div>
    </div>
  );
};
