import { useRef, useEffect } from "react";

export default function LidarCanvas({ points }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const c = canvasRef.current;
    const ctx = c.getContext("2d");
    const ox = c.width / 2, oy = c.height / 2, scale = 50;

    // clear background
    ctx.fillStyle = "#0b0b0b";
    ctx.fillRect(0, 0, c.width, c.height);

    // draw axes
    ctx.strokeStyle = "#333";
    ctx.beginPath();
    ctx.moveTo(0, oy);
    ctx.lineTo(c.width, oy);
    ctx.moveTo(ox, 0);
    ctx.lineTo(ox, c.height);
    ctx.stroke();

    // draw points
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.fillStyle = "#00f7ff";
    ctx.beginPath();
    for (const p of points) {
      const px = p.x * scale, py = p.y * scale;
      ctx.moveTo(px, py);
      ctx.arc(px, py, 1.2, 0, Math.PI * 2);
    }
    ctx.fill();
    ctx.restore();
  }, [points]);

  return (
    <canvas
      ref={canvasRef}
      width={600}
      height={600}
      className="rounded-xl shadow border border-gray-700 bg-black"
    />
  );
}