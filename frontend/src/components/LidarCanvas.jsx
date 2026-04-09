import { useRef, useEffect, useState } from "react";

export default function LidarCanvas({ points, nearest, size = 460 }) {
  const canvasRef = useRef(null);
  const [zoom, setZoom] = useState(1.0);
  const lastFrame = useRef(performance.now());

  useEffect(() => {
    const c = canvasRef.current;
    const ctx = c.getContext("2d");
    const w = c.width;
    const h = c.height;
    const ox = w / 2;
    const oy = h / 2;

    const baseScale = (size / 460) * 70;
    const scale = baseScale * zoom;

    // Fade trail
    ctx.fillStyle = "rgba(0,0,0,0.22)";
    ctx.fillRect(0, 0, w, h);

    // Grid rings
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.strokeStyle = "rgba(148,163,184,0.12)";
    ctx.lineWidth = 0.5;
    ctx.fillStyle = "rgba(148,163,184,0.35)";
    ctx.font = "9px monospace";
    for (let r = 0.5; r <= 5; r += 0.5) {
      ctx.beginPath();
      ctx.arc(0, 0, r * scale, 0, Math.PI * 2);
      ctx.stroke();
      if (r % 1 === 0) {
        ctx.scale(1, -1);
        ctx.fillText(`${r.toFixed(0)}m`, r * scale + 3, -2);
        ctx.scale(1, -1);
      }
    }
    ctx.restore();

    // Axes
    ctx.save();
    ctx.translate(ox, oy);
    ctx.strokeStyle = "rgba(51,65,85,0.5)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(-w / 2, 0); ctx.lineTo(w / 2, 0);
    ctx.moveTo(0, -h / 2); ctx.lineTo(0, h / 2);
    ctx.stroke();
    ctx.restore();

    // Alert circle
    ctx.save();
    ctx.translate(ox, oy);
    ctx.beginPath();
    ctx.arc(0, 0, 0.05 * scale, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(239,68,68,0.1)";
    ctx.strokeStyle = "rgba(239,68,68,0.3)";
    ctx.lineWidth = 1;
    ctx.fill();
    ctx.stroke();
    ctx.restore();

    // LiDAR points
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    for (const p of points) {
      const d = Math.sqrt(p.x * p.x + p.y * p.y);
      const hue = 220 - Math.min(d * 100, 180);
      ctx.fillStyle = `hsl(${hue},90%,60%)`;
      ctx.beginPath();
      ctx.arc(p.x * scale, p.y * scale, 1.5, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.restore();

    // Drone triangle
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    const s = 10;
    ctx.beginPath();
    ctx.moveTo(0, s);
    ctx.lineTo(-s / 2, -s / 2);
    ctx.lineTo(s / 2, -s / 2);
    ctx.closePath();
    ctx.fillStyle = "#60a5fa";
    ctx.fill();
    ctx.restore();

    // Compass
    const compassR = 30;
    const cx = w - compassR - 10;
    const cy = compassR + 10;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = "rgba(148,163,184,0.3)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(0, 0, compassR, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgba(148,163,184,0.5)";
    ctx.font = "9px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("N", 0, -compassR + 7);
    ctx.fillText("S", 0,  compassR - 7);
    ctx.fillText("W", -compassR + 7, 0);
    ctx.fillText("E",  compassR - 7, 0);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, -compassR + 4);
    ctx.strokeStyle = "#60a5fa";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();

    // Bottom HUD
    const now = performance.now();
    const dt  = now - lastFrame.current;
    lastFrame.current = now;
    const fps = (1000 / dt).toFixed(0);
    ctx.save();
    ctx.fillStyle = "rgba(148,163,184,0.6)";
    ctx.font = "10px monospace";
    ctx.fillText(
      `${nearest ? (nearest * 100).toFixed(1) : "--"} cm  ·  ${points.length} pts  ·  ${fps} fps  ·  ${(zoom * 100).toFixed(0)}%`,
      10, h - 10,
    );
    ctx.restore();
  }, [points, nearest, zoom]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const onWheel = (e) => {
      e.preventDefault();
      setZoom(z => Math.min(Math.max(z + (e.deltaY > 0 ? -0.1 : 0.1), 0.2), 5.0));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="rounded-xl bg-black select-none"
      style={{ border: "1px solid #2a3b26", width: "100%", height: "auto", maxHeight: "100%", aspectRatio: "1 / 1" }}
      title="Scroll to zoom"
    />
  );
}
