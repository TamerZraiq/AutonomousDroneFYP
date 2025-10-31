import { useEffect, useState } from "react";

export function useLidarStream() {
  const [points, setPoints] = useState([]);
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.hostname}:8000/ws/lidar`);
    ws.onopen = () => console.log("✅ WebSocket connected");
    ws.onclose = (e) => console.log("❌ WebSocket closed", e);
    ws.onerror = (e) => console.error("⚠ WebSocket error", e);

    ws.onopen = () => setStatus("live");
    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("error");
    ws.onmessage = (msg) => {
      const data = JSON.parse(msg.data);
      setPoints(data.x.map((x, i) => ({ x, y: data.y[i], c: data.c[i] })));
      console.log("WS DATA:", data);
      if (data.too_close === true) {
        console.warn(`⚠ Object too close: ${Math.round(data.nearest_distance * 100)} cm`);
        let alertBox = document.getElementById("lidar-alert");
        if (!alertBox) {
          alertBox = document.createElement("div");
          alertBox.id = "lidar-alert";
          alertBox.style.position = "fixed";
          alertBox.style.top = "10px";
          alertBox.style.right = "10px";
          alertBox.style.background = "#dc2626"; // red-600
          alertBox.style.color = "white";
          alertBox.style.padding = "10px 16px";
          alertBox.style.borderRadius = "8px";
          alertBox.style.fontWeight = "bold";
          alertBox.style.transition = "opacity 0.5s";
          document.body.appendChild(alertBox);
        }
        alertBox.textContent = `⚠ Object too close: ${Math.round(data.nearest_distance * 100)} cm`;
        alertBox.style.opacity = "1";
        setTimeout(() => (alertBox.style.opacity = "0"), 2000);
      }
      


    };


    return () => ws.close();
  }, []);

  return { points, status };
}
