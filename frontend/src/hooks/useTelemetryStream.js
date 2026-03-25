import { useEffect, useState } from "react";

const DEFAULT_TELEM = {
  connected:   false,
  state:       "UNKNOWN",
  armed:       false,
  flight_mode: "UNKNOWN",
  lat: 0, lon: 0,
  abs_alt: 0, rel_alt: 0,
  battery_pct: 0,
  local_north: 0, local_east: 0, local_down: 0,
  heading_deg: 0,
  mission:  { active: false, current_wp: 0, total_wp: 0, finished: false },
  offboard: { active: false, paused: false, current_wp: 0, total_wp: 0, finished: false },
  detections: [],
};

export function useTelemetryStream() {
  const [telem, setTelem]   = useState(DEFAULT_TELEM);
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    let ws;
    let reconnectTimer;
    let watchdog;

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);

      ws.onopen  = () => { setStatus("live"); resetWatchdog(); };
      ws.onclose = () => { setStatus("disconnected"); scheduleReconnect(); };
      ws.onerror = () => { setStatus("error"); };

      ws.onmessage = (msg) => {
        resetWatchdog();
        try { setTelem(JSON.parse(msg.data)); } catch {}
      };
    }

    function resetWatchdog() {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => { ws?.close(); }, 6000);
    }

    function scheduleReconnect() {
      clearTimeout(watchdog);
      reconnectTimer = setTimeout(connect, 3000);
    }

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      clearTimeout(watchdog);
      ws?.close();
    };
  }, []);

  return { telem, status };
}
