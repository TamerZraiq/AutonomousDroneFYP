import { useRef, useEffect, useState } from "react";

export default function LidarCanvas({ points, nearest }) {
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

    const baseScale = 80; // px per meter
    const scale = baseScale * zoom;
    const fade = 0.25;

    // === 1. Fade trail ===
    ctx.fillStyle = `rgba(0,0,0,${fade})`;
    ctx.fillRect(0, 0, w, h);

    // === 2. Grid + labels ===
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.strokeStyle = "rgba(120,120,120,0.25)";
    ctx.lineWidth = 0.5;
    ctx.font = "10px monospace";
    ctx.scale(1, -1);
    ctx.fillStyle = "rgba(180,180,180,0.5)";
    for (let r = 0.5; r <= 5; r += 0.5) {
      ctx.beginPath();
      ctx.arc(0, 0, r * scale, 0, Math.PI * 2);
      ctx.stroke();
      if (r % 1 === 0) ctx.fillText(`${r.toFixed(0)} m`, r * scale + 4, -2);
    }
    ctx.scale(1, -1);
    ctx.restore();

    // === 3. Axes ===
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.strokeStyle = "rgba(80,80,80,0.3)";
    ctx.beginPath();
    ctx.moveTo(-w / 2, 0);
    ctx.lineTo(w / 2, 0);
    ctx.moveTo(0, -h / 2);
    ctx.lineTo(0, h / 2);
    ctx.stroke();
    ctx.restore();

    // === 4. Alert circle (5 cm) ===
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.beginPath();
    ctx.arc(0, 0, 0.05 * scale, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,0,0,0.1)";
    ctx.strokeStyle = "rgba(255,0,0,0.3)";
    ctx.lineWidth = 1;
    ctx.fill();
    ctx.stroke();
    ctx.restore();

    // === 5. LiDAR points ===
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    for (const p of points) {
      const d = Math.sqrt(p.x * p.x + p.y * p.y);
      const hue = 240 - Math.min(d * 120, 240);
      ctx.fillStyle = `hsl(${hue},100%,50%)`;
      ctx.beginPath();
      ctx.arc(p.x * scale, p.y * scale, 1.5, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.restore();

    // === 6. Facing triangle ===
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.beginPath();
    const s = 12;
    ctx.moveTo(0, s);
    ctx.lineTo(-s / 2, -s / 2);
    ctx.lineTo(s / 2, -s / 2);
    ctx.closePath();
    ctx.fillStyle = "#00ffff";
    ctx.shadowColor = "#00ffff";
    ctx.shadowBlur = 6;
    ctx.fill();
    ctx.restore();

    // === 7. Compass ===
    const compassR = 35;
    ctx.save();
    ctx.translate(w - compassR - 10, compassR + 10);
    ctx.strokeStyle = "rgba(200,200,200,0.5)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(0, 0, compassR, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "white";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("N", 0, -compassR + 8);
    ctx.fillText("S", 0, compassR - 8);
    ctx.fillText("W", -compassR + 8, 0);
    ctx.fillText("E", compassR - 8, 0);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, -compassR + 5);
    ctx.strokeStyle = "#00ffff";
    ctx.stroke();
    ctx.restore();

    // === 8. Telemetry ===
    const now = performance.now();
    const dt = now - lastFrame.current;
    lastFrame.current = now;
    const fps = (1000 / dt).toFixed(1);
    ctx.save();
    ctx.fillStyle = "rgba(200,200,200,0.8)";
    ctx.font = "12px monospace";
    ctx.fillText(
      `Nearest: ${nearest ? (nearest * 100).toFixed(1) : "--"} cm | FPS: ${fps} | Points: ${
        points.length
      } | Zoom: ${(zoom * 100).toFixed(0)}%`,
      10,
      h - 12
    );
    ctx.restore();
  }, [points, nearest, zoom]);

  // === 9. Zoom event handling ===
  useEffect(() => {
    const canvas = canvasRef.current;
    const handleWheel = (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1; // scroll up -> zoom in
      setZoom((z) => Math.min(Math.max(z + delta, 0.2), 5.0));
    };
    canvas.addEventListener("wheel", handleWheel);
    return () => canvas.removeEventListener("wheel", handleWheel);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      width={600}
      height={600}
      className="rounded-xl border border-zinc-700 shadow-lg bg-black select-none"
      title="Scroll to zoom (0.2x–5x)"
    />
  );
}
