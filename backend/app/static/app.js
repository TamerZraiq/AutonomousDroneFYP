(function() {
  const canvas = document.getElementById("lidarCanvas");
  const ctx = canvas.getContext("2d");
  const statusEl = document.getElementById("status");
  const pfEl = document.getElementById("pf");
  const clearBtn = document.getElementById("clearBtn");

  // world scale config
  // canvas coordinates: (0,0) center, +y up, +x right
  const metersToPixels = 50; // 1 m = 50 px (tune)
  const originX = canvas.width / 2;
  const originY = canvas.height / 2;

  function clearCanvas() {
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    // draw axes
    ctx.strokeStyle = "#333";
    ctx.beginPath();
    ctx.moveTo(0, originY); ctx.lineTo(canvas.width, originY);
    ctx.moveTo(originX, 0); ctx.lineTo(originX, canvas.height);
    ctx.stroke();
  }

  clearBtn.addEventListener("click", clearCanvas);
  clearCanvas();

  // Build WS URL that works from LAN or loopback
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${proto}://${location.host}/ws/lidar`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusEl.textContent = "live";
    statusEl.style.color = "lime";
  };

  ws.onclose = () => {
    statusEl.textContent = "disconnected";
    statusEl.style.color = "orange";
  };

  ws.onerror = () => {
    statusEl.textContent = "error";
    statusEl.style.color = "red";
  };

  // Fast draw loop: redraw fresh each frame (no trail). If you want a trail, remove clearCanvas() in onmessage
  ws.onmessage = (event) => {
    const t0 = performance.now();
    const data = JSON.parse(event.data); // {x:[], y:[], c:[]}
    const xs = data.x, ys = data.y, cs = data.c;
    pfEl.textContent = xs.length;

    clearCanvas();
    ctx.save();
    ctx.translate(originX, originY);
    ctx.scale(1, -1); // flip Y so +Y is up

    // Draw points
    // Batch optimized: single path for many points
    ctx.fillStyle = "#77e1ff";
    ctx.beginPath();
    for (let i = 0; i < xs.length; i++) {
      const px = xs[i] * metersToPixels;
      const py = ys[i] * metersToPixels;
      // quick culling
      if (px < -originX || px > originX || py < -originY || py > originY) continue;
      ctx.moveTo(px, py);
      ctx.arc(px, py, 1.2, 0, Math.PI * 2);
    }
    ctx.fill();

    ctx.restore();
    const t1 = performance.now();
    // You can print (t1 - t0) if you want frame time
  };
})();
