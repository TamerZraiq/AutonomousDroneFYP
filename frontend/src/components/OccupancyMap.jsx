import { useEffect, useRef } from "react";

const FREE     = 0;
const OCCUPIED = 1;

export default function OccupancyMap({ map, size = 460 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !map.data.length) return;

    const { cells, data, drone_row, drone_col, heading_deg, detections } = map;
    const size   = canvas.width;
    const cellPx = size / cells;

    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, size, size);

    // Grid cells
    for (let r = 0; r < cells; r++) {
      for (let c = 0; c < cells; c++) {
        const val = data[r * cells + c];
        if      (val === FREE)     ctx.fillStyle = "rgba(34,197,94,0.4)";
        else if (val === OCCUPIED) ctx.fillStyle = "rgba(239,68,68,0.85)";
        else continue;
        ctx.fillRect(c * cellPx, r * cellPx, cellPx, cellPx);
      }
    }

    // Drone dot + heading arrow
    const dx  = drone_col * cellPx + cellPx / 2;
    const dy  = drone_row * cellPx + cellPx / 2;
    const rad = (heading_deg - 90) * (Math.PI / 180);

    ctx.save();
    ctx.translate(dx, dy);
    ctx.beginPath();
    ctx.arc(0, 0, 7, 0, Math.PI * 2);
    ctx.fillStyle = "#60a5fa";
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(rad) * 14, Math.sin(rad) * 14);
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();

    // Detection markers — drawn on top of everything so they're always visible
    for (const d of detections) {
      const cx = d.col * cellPx + cellPx / 2;
      const cy = d.row * cellPx + cellPx / 2;
      // filled yellow dot
      ctx.beginPath();
      ctx.arc(cx, cy, 6, 0, Math.PI * 2);
      ctx.fillStyle = "#fbbf24";
      ctx.fill();
      // white ring so it pops against any background
      ctx.beginPath();
      ctx.arc(cx, cy, 9, 0, Math.PI * 2);
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // Scale bar — 1 m
    const meterPx = (1 / map.resolution) * cellPx;
    ctx.fillStyle = "rgba(148,163,184,0.8)";
    ctx.fillRect(8, size - 14, meterPx, 2);
    ctx.font = "9px monospace";
    ctx.fillStyle = "rgba(148,163,184,0.6)";
    ctx.fillText("1 m", 8 + meterPx + 4, size - 10);

  }, [map]);

  function savePNG() {
    const a = document.createElement("a");
    a.download = `occupancy_map_${Date.now()}.png`;
    a.href = canvasRef.current.toDataURL();
    a.click();
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <canvas
        ref={canvasRef}
        id="occupancy-canvas"
        width={size}
        height={size}
        className="rounded-xl"
        style={{ background: "#0f1a0c", border: "1px solid #2a3b26", width: "100%", height: "auto", maxHeight: "100%", aspectRatio: "1 / 1" }}
      />
      <button
        onClick={savePNG}
        className="text-xs text-slate-600 hover:text-slate-400 transition-colors border border-slate-800 hover:border-slate-700 px-3 py-1.5 rounded-lg"
      >
        Save PNG
      </button>
    </div>
  );
}
