import { useEffect, useState } from "react";

export function useLidarStream() {
  const [points, setPoints] = useState([]);
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.hostname}:8000/ws/lidar`);


    ws.onopen = () => setStatus("live");
    ws.onclose = () => setStatus("disconnected");
    ws.onerror = () => setStatus("error");
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);
      const pts = d.x.map((x, i) => ({ x, y: d.y[i], c: d.c[i] }));
      setPoints(pts);
    };

    return () => ws.close();
  }, []);

  return { points, status };
}
