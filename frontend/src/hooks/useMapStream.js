import { useEffect, useState } from "react";

const EMPTY_MAP = {
  cells: 200,
  size_m: 20,
  resolution: 0.1,
  data: [],
  drone_row: 100,
  drone_col: 100,
  heading_deg: 0,
  detections: [],
};

export function useMapStream() {
  const [map, setMap]       = useState(EMPTY_MAP);
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    let ws, reconnectTimer, watchdog;

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/map`);
      ws.onopen  = () => { setStatus("live"); resetWatchdog(); };
      ws.onclose = () => { setStatus("disconnected"); scheduleReconnect(); };
      ws.onerror = () => setStatus("error");
      ws.onmessage = (msg) => {
        resetWatchdog();
        try { setMap(JSON.parse(msg.data)); } catch {}
      };
    }

    function resetWatchdog() {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => ws?.close(), 8000);
    }
    function scheduleReconnect() {
      clearTimeout(watchdog);
      reconnectTimer = setTimeout(connect, 3000);
    }

    connect();
    return () => { clearTimeout(reconnectTimer); clearTimeout(watchdog); ws?.close(); };
  }, []);

  return { map, status };
}
