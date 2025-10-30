import { useRef, useEffect } from "react";

export default function LidarCanvas({ points }) {
  const ref = useRef();

  useEffect(() => {
    const c = ref.current;
    const ctx = c.getContext("2d");
    const ox = c.width / 2, oy = c.height / 2, scale = 50;

    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, c.width, c.height);

    ctx.strokeStyle = "rgba(80,80,80,0.4)";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(ox, 0);
    ctx.lineTo(ox, c.height);
    ctx.moveTo(0, oy);
    ctx.lineTo(c.width, oy);
    ctx.stroke();

    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(1, -1);
    ctx.fillStyle = "#00e5ff";
    ctx.shadowColor = "#00e5ff";
    ctx.shadowBlur = 6;
    ctx.beginPath();
    for (const p of points) {
      const px = p.x * scale, py = p.y * scale;
      ctx.moveTo(px, py);
      ctx.arc(px, py, 1.5, 0, Math.PI * 2);
    }
    ctx.fill();
    ctx.restore();
  }, [points]);

  return (
    <canvas
      ref={ref}
      width={600}
      height={600}
      className="w-full h-full rounded-xl"
    />
  );
}
