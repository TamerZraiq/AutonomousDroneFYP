import { useState, useRef, useEffect } from "react";
import { useLidarStream }     from "./hooks/useLidarStream";
import { useTelemetryStream } from "./hooks/useTelemetryStream";
import { useMapStream }       from "./hooks/useMapStream";
import LidarCanvas   from "./components/LidarCanvas";
import OccupancyMap  from "./components/OccupancyMap";
import AICamFeed     from "./components/AICamFeed";
import TelemetryBox  from "./components/TelemetryBox";
import "./index.css";

async function api(path, method = "GET", body = null) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : null,
  });
  return res.json();
}

async function exportPDF(detections) {
  const { jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const doc = new jsPDF();
  const now = new Date().toLocaleString();

  // Fetch full report (includes frame_b64 per detection)
  let reportDetections = detections;
  try {
    const report = await api("/api/drone/report/json");
    if (report.detections?.length > 0) reportDetections = report.detections;
  } catch { /* fall back to WS detections */ }

  doc.setFontSize(22); doc.setTextColor(30, 30, 30);
  doc.text("AeroDrop SAR Mission Report", 14, 22);
  doc.setFontSize(10); doc.setTextColor(120);
  doc.text(`Generated: ${now}`, 14, 30);

  // Occupancy map snapshot
  const canvas = document.getElementById("occupancy-canvas");
  if (canvas) {
    doc.setFontSize(13); doc.setTextColor(30);
    doc.text("Occupancy Map", 14, 44);
    doc.addImage(canvas.toDataURL("image/png"), "PNG", 14, 48, 100, 100);
  }

  // Detections summary table
  doc.setFontSize(13); doc.setTextColor(30);
  doc.text("Detections", 14, 162);
  autoTable(doc, {
    startY: 167,
    head: [["#", "Object", "Confidence", "North (m)", "East (m)", "Time"]],
    body: reportDetections.map((d, i) => [
      i + 1, d.object_class,
      `${(d.confidence * 100).toFixed(1)}%`,
      d.north.toFixed(2), d.east.toFixed(2),
      new Date(d.timestamp * 1000).toLocaleTimeString(),
    ]),
    theme: "grid",
  });

  // One page per detection that has a camera frame
  reportDetections.forEach((d, i) => {
    if (!d.frame_b64) return;
    doc.addPage();
    doc.setFontSize(15); doc.setTextColor(30);
    doc.text(`Detection ${i + 1} — ${d.object_class}`, 14, 20);
    doc.setFontSize(10); doc.setTextColor(80);
    doc.text(
      `Confidence: ${(d.confidence * 100).toFixed(1)}%  |  N ${d.north.toFixed(2)} m  E ${d.east.toFixed(2)} m  |  ${new Date(d.timestamp * 1000).toLocaleTimeString()}`,
      14, 28,
    );
    doc.addImage(`data:image/jpeg;base64,${d.frame_b64}`, "JPEG", 14, 35, 182, 136);
  });

  doc.save(`aerodrop_report_${Date.now()}.pdf`);
}

const TARGETS = ["person", "backpack", "phone", "fire", "vehicle"];
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

const BG        = "#161d14";
const CARD_BG   = "rgba(242, 235, 215, 0.07)";
const CARD_BORDER = "rgba(242, 235, 215, 0.13)";
const PANEL_BG  = "rgba(242, 235, 215, 0.04)";
const PANEL_BORDER = "rgba(242, 235, 215, 0.08)";

export default function App() {
  const { points, nearest } = useLidarStream();
  const { telem }           = useTelemetryStream();
  const { map }             = useMapStream();

  const missionRef = useRef(null);
  const dataRef    = useRef(null);

  const [target,    setTarget]    = useState("person");
  const [rowLength, setRowLength] = useState(3.0);
  const [rows,      setRows]      = useState(4);
  const [altitude,  setAltitude]  = useState(1.2);
  const [busy,      setBusy]      = useState(false);
  const [cmdError,  setCmdError]  = useState(null);
  const [detectionFrames, setDetectionFrames] = useState({});
  const [scanRunning, setScanRunning] = useState(false);

  const detectionCount = telem.detections?.length ?? 0;
  useEffect(() => {
    if (detectionCount === 0) { setDetectionFrames({}); return; }
    api("/api/drone/report/json").then(data => {
      const frames = {};
      (data.detections || []).forEach((d, i) => { if (d.frame_b64) frames[i] = d.frame_b64; });
      setDetectionFrames(frames);
    }).catch(() => {});
  }, [detectionCount]);

  // Poll scan status so the button reflects reality after page reload
  useEffect(() => {
    const id = setInterval(() => {
      api("/api/demo/scan/status").then(d => setScanRunning(!!d.running)).catch(() => {});
    }, 2000);
    return () => clearInterval(id);
  }, []);

  async function toggleScan() {
    setBusy(true); setCmdError(null);
    try {
      if (scanRunning) {
        await api("/api/demo/scan/stop", "POST");
        setScanRunning(false);
      } else {
        await api("/api/demo/scan/start", "POST", { target });
        setScanRunning(true);
      }
    } catch (e) { setCmdError(e.message); } finally { setBusy(false); }
  }

  const isConnected = telem.connected;
  const isAirborne  = ["TAKEOFF", "MISSION", "RTL"].includes(telem.state);
  const isMission   = telem.state === "MISSION";
  const detections  = telem.detections || [];
  const coverage    = (rowLength * rows * 0.8).toFixed(1);

  async function cmd(path, body = null) {
    setBusy(true); setCmdError(null);
    try {
      const res = await api(path, "POST", body);
      if (res.error) setCmdError(res.error);
    } catch (e) {
      setCmdError(e.message);
    } finally { setBusy(false); }
  }

  const scrollTo = ref => ref.current?.scrollIntoView({ behavior: "smooth" });

  return (
    <div style={{ background: BG }}>

      {/* ── Error toast ──────────────────────────────────────────────────── */}
      {cmdError && (
        <div className="fixed top-4 right-4 z-50 text-sm px-4 py-3 rounded-xl shadow-2xl flex items-start gap-3 max-w-sm"
             style={{ background: "#2a1010", border: "1px solid #5a2020", color: "#fca5a5" }}>
          <span className="flex-1 leading-snug">{cmdError}</span>
          <button onClick={() => setCmdError(null)} style={{ color: "#f87171" }}>✕</button>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 1 — HERO
      ══════════════════════════════════════════════════════════════════ */}
      <section className="hero-grid-bg min-h-screen flex flex-col items-center justify-center text-center px-6 relative overflow-hidden">

        {/* Drone CAD — multiply blend removes white bg */}
        <img
          src="/static/drone-cad.png" alt="" aria-hidden="true"
          className="absolute pointer-events-none select-none"
          style={{
            width: "70%", maxWidth: 760,
            top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            mixBlendMode: "multiply",
            opacity: 0.6,
            zIndex: 0,
          }}
          onError={e => { e.currentTarget.style.display = "none"; }}
        />

        {/* Text — above image */}
        <div className="relative z-10 w-full" style={{ maxWidth: "90vw" }}>
          <p className="text-xs font-semibold tracking-[0.35em] uppercase mb-8"
             style={{ color: "#d8e4c8" }}>
            Autonomous Search &amp; Rescue
          </p>

          <h1
            className="font-black tracking-tighter leading-none mb-5 text-center w-full text-white"
            style={{ fontSize: "clamp(5rem, 17vw, 14rem)" }}
          >
            AERODROP
          </h1>

          <p className="font-bold uppercase tracking-widest text-sm mb-12"
             style={{ color: "#d4d820" }}>
            An autonomous drone for indoor mapping and delivery
          </p>

          <button
            onClick={() => scrollTo(missionRef)}
            className="px-10 py-3 text-sm font-bold uppercase tracking-widest rounded-xl transition-colors"
            style={{ background: "#d4d820", color: "#1a2010" }}
            onMouseEnter={e => e.currentTarget.style.background = "#e0e42a"}
            onMouseLeave={e => e.currentTarget.style.background = "#d4d820"}
          >
            Begin Mission
          </button>
        </div>

        <div className="absolute bottom-8 z-10 flex flex-col items-center gap-1.5 text-xs tracking-widest uppercase"
             style={{ color: "rgba(255,255,255,0.35)" }}>
          <span>Scroll to configure</span>
          <span className="text-base animate-bounce">↓</span>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 2 — MISSION SETUP
      ══════════════════════════════════════════════════════════════════ */}
      <section ref={missionRef} className="min-h-screen px-6 py-16"
               style={{ background: BG, borderTop: "1px solid #2a3b26" }}>
        <div className="max-w-5xl mx-auto">

          <div className="mb-10">
            <p className="section-label mb-2 tracking-[0.25em]">Step 01</p>
            <h2 className="text-4xl font-bold text-white">Mission Setup</h2>
          </div>

          {/* Status strip */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-10 px-4 py-3 rounded-xl"
               style={{ background: CARD_BG, border: `1px solid ${CARD_BORDER}` }}>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-400" : "bg-red-400"}`} />
              <span className="text-sm" style={{ color: "#c8d8c0" }}>
                FC {isConnected ? "Connected" : "Offline"}
              </span>
            </div>
            <span style={{ color: "#2a3b26" }}>|</span>
            <span className="text-sm font-mono" style={{ color: "#c8d8c0" }}>{telem.state}</span>
            <span style={{ color: "#2a3b26" }}>|</span>
            <span className={`text-sm font-semibold ${telem.armed ? "text-red-400" : ""}`}
                  style={!telem.armed ? { color: "#5a7252" } : {}}>
              {telem.armed ? "Armed" : "Disarmed"}
            </span>
            <span style={{ color: "#2a3b26" }}>|</span>
            <span className="text-sm font-mono" style={{ color: "#6b8a60" }}>{telem.flight_mode}</span>
            <span style={{ color: "#2a3b26" }}>|</span>
            <span className="text-sm font-mono" style={{ color: "#6b8a60" }}>{telem.rel_alt.toFixed(2)} m</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* ── Mission Parameters ──────────────────────────────────── */}
            <div className="card p-6 space-y-7">
              <h3 className="font-semibold text-white text-lg">Mission Parameters</h3>

              <div>
                <label className="stat-label block mb-2">Search Target</label>
                <select value={target} onChange={e => setTarget(e.target.value)} className="input">
                  {TARGETS.map(t => <option key={t} value={t}>{cap(t)}</option>)}
                </select>
              </div>

              <div>
                <div className="flex justify-between items-center mb-3">
                  <label className="stat-label">Row Length</label>
                  <span className="text-sm font-mono font-bold" style={{ color: "#d4d820" }}>{rowLength.toFixed(1)} m</span>
                </div>
                <input type="range" min="1" max="10" step="0.5"
                  value={rowLength} onChange={e => setRowLength(+e.target.value)} />
                <div className="flex justify-between text-xs mt-1.5" style={{ color: "#3a4e34" }}>
                  <span>1 m</span><span>10 m</span>
                </div>
              </div>

              <div>
                <label className="stat-label block mb-3">Number of Rows</label>
                <div className="flex items-center gap-4">
                  <button onClick={() => setRows(r => Math.max(1, r - 1))}
                    className="w-9 h-9 rounded-lg flex items-center justify-center text-lg transition-colors"
                    style={{ background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`, color: "#c8d8c0" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#1e2b1a"}
                    onMouseLeave={e => e.currentTarget.style.background = "#161d14"}
                  >−</button>
                  <span className="text-3xl font-black text-white w-10 text-center tabular-nums">{rows}</span>
                  <button onClick={() => setRows(r => Math.min(20, r + 1))}
                    className="w-9 h-9 rounded-lg flex items-center justify-center text-lg transition-colors"
                    style={{ background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`, color: "#c8d8c0" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#1e2b1a"}
                    onMouseLeave={e => e.currentTarget.style.background = "#161d14"}
                  >+</button>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-3">
                  <label className="stat-label">Cruise Altitude</label>
                  <span className="text-sm font-mono font-bold" style={{ color: "#d4d820" }}>{altitude.toFixed(1)} m</span>
                </div>
                <input type="range" min="0.5" max="3" step="0.1"
                  value={altitude} onChange={e => setAltitude(+e.target.value)} />
                <div className="flex justify-between text-xs mt-1.5" style={{ color: "#3a4e34" }}>
                  <span>0.5 m</span><span>3.0 m</span>
                </div>
              </div>

              <div className="p-4 rounded-xl space-y-2"
                   style={{ background: PANEL_BG, border: `1px solid ${PANEL_BORDER}` }}>
                <div className="flex justify-between">
                  <span className="stat-label">Est. coverage</span>
                  <span className="text-sm font-mono font-bold" style={{ color: "#d4d820" }}>{coverage} m²</span>
                </div>
                <div className="flex justify-between">
                  <span className="stat-label">Waypoints</span>
                  <span className="stat-value">{rows + 1}</span>
                </div>
                <div className="flex justify-between">
                  <span className="stat-label">Row spacing</span>
                  <span className="stat-value">0.8 m</span>
                </div>
              </div>
            </div>

            {/* ── Flight Control ──────────────────────────────────────── */}
            <div className="card p-6 space-y-3">
              <h3 className="font-semibold text-white text-lg mb-1">Flight Control</h3>

              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => cmd("/api/drone/arm")}
                  disabled={busy || telem.state !== "IDLE" || !isConnected}
                  className="btn-primary py-2.5">Arm</button>
                <button onClick={() => cmd("/api/drone/disarm")}
                  disabled={busy || telem.state !== "ARMED"}
                  className="btn-secondary py-2.5">Disarm</button>
              </div>

              <button onClick={() => cmd("/api/drone/takeoff", { alt: altitude })}
                disabled={busy || telem.state !== "ARMED"}
                className="btn-primary w-full py-2.5">
                Takeoff
                <span className="opacity-50 text-xs ml-2">→ {altitude.toFixed(1)} m</span>
              </button>

              <button onClick={() => cmd("/api/drone/motor_test", { motor: 0, throttle: 10, duration: 3 })}
                disabled={busy || !isConnected}
                className="btn-secondary w-full py-2"
                style={{ fontSize: "0.8rem", opacity: 0.8 }}>
                Motor Test (all, 10%, 3 s)
              </button>

              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => cmd("/api/drone/rtl")}
                  disabled={busy || !isAirborne}
                  className="btn-secondary py-2.5">RTL</button>
                <button onClick={() => cmd("/api/drone/land")}
                  disabled={busy || !isAirborne}
                  className="btn-secondary py-2.5">Land</button>
              </div>

              <button onClick={() => cmd("/api/drone/reset")}
                disabled={busy || !["LANDED","ARMED","EMERGENCY"].includes(telem.state)}
                className="btn-ghost w-full py-2 text-xs">Reset State</button>

              <div className="grid grid-cols-3 gap-2">
                <button onClick={() => cmd("/api/drone/gripper/open")}
                  disabled={busy}
                  className="btn-secondary py-2 text-xs">Gripper Open</button>
                <button onClick={() => cmd("/api/drone/gripper/drop")}
                  disabled={busy}
                  className="btn-primary py-2 text-xs">Drop</button>
                <button onClick={() => cmd("/api/drone/gripper/close")}
                  disabled={busy}
                  className="btn-secondary py-2 text-xs">Gripper Close</button>
              </div>

              <button onClick={() => cmd("/api/drone/emergency")}
                className="w-full py-3 rounded-lg font-bold text-sm transition-colors"
                style={{ background: "#7f1d1d", color: "#fca5a5", border: "1px solid #991b1b" }}
                onMouseEnter={e => e.currentTarget.style.background = "#991b1b"}
                onMouseLeave={e => e.currentTarget.style.background = "#7f1d1d"}
              >⚠ Emergency Stop</button>

              <div className="pt-4 space-y-3" style={{ borderTop: "1px solid #2a3b26" }}>
                <h4 className="section-label">Mission</h4>

                {!isMission ? (
                  <button
                    onClick={() => cmd("/api/drone/task/start", { target, row_length: rowLength, rows, altitude })}
                    disabled={busy || !isAirborne}
                    className="btn-primary w-full py-3 text-base">
                    Start SAR Mission
                  </button>
                ) : (
                  <div className="space-y-3">
                    {telem.offboard?.active && (
                      <div>
                        <div className="flex justify-between text-xs mb-1.5" style={{ color: "#6b8a60" }}>
                          <span>WP {telem.offboard.current_wp} / {telem.offboard.total_wp}</span>
                          <span>
                            {telem.offboard.blocked && <span style={{ color: "#d4d820" }}>⚠ Blocked</span>}
                            {telem.offboard.paused  && <span style={{ color: "#d4d820" }}>⏸ Paused</span>}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "#2a3b26" }}>
                          <div className="h-full rounded-full transition-all duration-500"
                               style={{ width: `${(telem.offboard.current_wp / (telem.offboard.total_wp || 1)) * 100}%`, background: "#d4d820" }} />
                        </div>
                      </div>
                    )}
                    <div className="grid grid-cols-3 gap-2">
                      <button onClick={() => cmd("/api/drone/task/pause")}  className="btn-secondary text-xs py-1.5">Pause</button>
                      <button onClick={() => cmd("/api/drone/task/resume")} className="btn-secondary text-xs py-1.5">Resume</button>
                      <button onClick={() => cmd("/api/drone/task/cancel")} className="btn-secondary text-xs py-1.5">Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ── Demo Controls ──────────────────────────────────────────── */}
          <div className="card p-6 mt-6">
            <div className="flex items-center gap-3 mb-5">
              <h3 className="font-semibold text-white text-lg">Demo Mode</h3>
              <span className="text-xs px-2 py-0.5 rounded font-mono"
                    style={{ background: "#1a2b10", color: "#d4d820", border: "1px solid #2a4a18" }}>
                no-fly
              </span>
              <span className="text-xs" style={{ color: "#3a4e34" }}>
                Uses real LiDAR + real camera AI — no flight required
              </span>
            </div>

            <div className="space-y-4">
              {/* Live scan */}
              <div className="flex items-center gap-4 p-4 rounded-xl"
                   style={{ background: PANEL_BG, border: `1px solid ${PANEL_BORDER}` }}>
                <div className="flex items-center gap-2 flex-1">
                  <span className={`w-2 h-2 rounded-full ${scanRunning ? "bg-green-400 animate-pulse" : "bg-gray-600"}`} />
                  <span className="text-sm font-mono" style={{ color: scanRunning ? "#4ade80" : "#5a7252" }}>
                    {scanRunning ? "Scanning — LiDAR mapping + camera detection active" : "Scan stopped"}
                  </span>
                </div>
                <button onClick={toggleScan} disabled={busy}
                  className={scanRunning ? "btn-secondary text-sm px-4 py-2" : "btn-primary text-sm px-4 py-2"}>
                  {scanRunning ? "Stop Scan" : "Start Live Scan"}
                </button>
                <button onClick={() => cmd("/api/demo/capture", "POST")} disabled={busy}
                  className="btn-secondary text-sm px-4 py-2">
                  Capture Frame
                </button>
                <button onClick={() => cmd("/api/drone/detections/clear")} disabled={busy}
                  className="btn-ghost text-xs px-3 py-2">
                  Clear
                </button>
              </div>

              {/* Force state machine */}
              <div>
                <p className="stat-label mb-2">Force State Machine (for recording)</p>
                <div className="flex flex-wrap gap-2">
                  {["IDLE","ARMED","TAKEOFF","MISSION","RTL","LANDED","EMERGENCY"].map(s => (
                    <button key={s}
                      onClick={() => cmd(`/api/demo/state/${s}`)}
                      disabled={busy}
                      className="px-3 py-1 text-xs font-mono rounded-lg transition-colors disabled:opacity-40"
                      style={{
                        background: telem.state === s ? "#1a3a10" : PANEL_BG,
                        border: `1px solid ${telem.state === s ? "#2a6a18" : PANEL_BORDER}`,
                        color: telem.state === s ? "#d4d820" : "#c8d8c0",
                      }}
                      onMouseEnter={e => { if (telem.state !== s) e.currentTarget.style.background = "#1e2b1a"; }}
                      onMouseLeave={e => { if (telem.state !== s) e.currentTarget.style.background = PANEL_BG; }}
                    >{s}</button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-14 flex justify-center">
            <button onClick={() => scrollTo(dataRef)}
              className="flex flex-col items-center gap-2 text-xs tracking-widest uppercase transition-colors"
              style={{ color: "#3a4e34" }}
              onMouseEnter={e => e.currentTarget.style.color = "#6b8a60"}
              onMouseLeave={e => e.currentTarget.style.color = "#3a4e34"}
            >
              <span>View Live Data</span>
              <span className="text-base">↓</span>
            </button>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          SECTION 3 — LIVE DATA  (h-screen, no internal scrolling)
      ══════════════════════════════════════════════════════════════════ */}
      <section ref={dataRef} className="h-screen overflow-hidden flex flex-col px-5 py-4"
               style={{ background: BG, borderTop: "1px solid #2a3b26" }}>

        {/* Header row */}
        <div className="flex-none flex items-center justify-between mb-3">
          <div className="flex items-center gap-6">
            <div>
              <p className="section-label tracking-[0.25em]">Step 02</p>
              <h2 className="text-2xl font-bold text-white leading-tight">Live Data</h2>
            </div>
            {/* Status pills */}
            <div className="hidden sm:flex items-center gap-2 flex-wrap">
              <span className={`text-xs px-2 py-1 rounded-md font-medium ${isConnected ? "text-green-300" : "text-red-300"}`}
                    style={{ background: isConnected ? "#14290f" : "#290f0f", border: `1px solid ${isConnected ? "#1a4a12" : "#4a1212"}` }}>
                {isConnected ? "FC Live" : "FC Offline"}
              </span>
              <span className="text-xs px-2 py-1 rounded-md font-mono" style={{ background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`, color: "#c8d8c0" }}>
                {telem.state}
              </span>
              {telem.armed && (
                <span className="text-xs px-2 py-1 rounded-md font-bold text-red-300" style={{ background: "#290f0f", border: "1px solid #4a1212" }}>
                  ARMED
                </span>
              )}
            </div>
          </div>
          <button onClick={() => exportPDF(detections)}
            className="btn-secondary text-xs">
            Export PDF
          </button>
        </div>

        {/* Data grid — fills remaining height */}
        <div className="flex-1 min-h-0 grid gap-3"
             style={{ gridTemplateColumns: "repeat(6, 1fr)", gridTemplateRows: "1fr 1fr 100px" }}>

          {/* Telemetry — cols 1-2, row 1 */}
          <div className="card p-4 overflow-auto" style={{ gridColumn: "1 / 3", gridRow: "1 / 2" }}>
            <p className="section-label mb-4">Telemetry</p>
            <TelemetryBox />
          </div>

          {/* Camera — cols 1-2, row 2 */}
          <div className="card p-4 overflow-hidden flex flex-col" style={{ gridColumn: "1 / 3", gridRow: "2 / 3" }}>
            <p className="section-label mb-2">Camera Feed</p>
            <div className="flex-1 flex items-center justify-center min-h-0">
              <AICamFeed />
            </div>
          </div>

          {/* LiDAR — cols 3-4, rows 1-2 */}
          <div className="card p-4 overflow-hidden flex flex-col" style={{ gridColumn: "3 / 5", gridRow: "1 / 3" }}>
            <p className="section-label mb-2">LiDAR</p>
            <div className="flex-1 min-h-0 overflow-hidden">
              <LidarCanvas points={points} nearest={nearest} size={460} />
            </div>
          </div>

          {/* Map — cols 5-6, rows 1-2 */}
          <div className="card p-4 overflow-hidden flex flex-col" style={{ gridColumn: "5 / 7", gridRow: "1 / 3" }}>
            <p className="section-label mb-2">Occupancy Map</p>
            <div className="flex-1 min-h-0 overflow-hidden">
              <OccupancyMap map={map} size={460} />
            </div>
          </div>

          {/* Detections — full width, fixed row */}
          <div className="card px-4 py-3 overflow-hidden flex flex-col" style={{ gridColumn: "span 6" }}>
            <div className="flex items-center justify-between mb-2 flex-none">
              <p className="section-label">
                Detections <span className="ml-1 normal-case font-mono" style={{ color: "#c8d8c0" }}>{detections.length}</span>
              </p>
              {detections.length > 0 && (
                <button onClick={() => cmd("/api/drone/detections/clear")}
                  className="text-xs transition-colors" style={{ color: "#3a4e34" }}
                  onMouseEnter={e => e.currentTarget.style.color = "#6b8a60"}
                  onMouseLeave={e => e.currentTarget.style.color = "#3a4e34"}
                >Clear</button>
              )}
            </div>
            {detections.length === 0 ? (
              <p className="text-sm" style={{ color: "#3a4e34" }}>No detections yet — start a mission to begin scanning.</p>
            ) : (
              <div className="flex gap-3 overflow-x-auto pb-1">
                {detections.map((d, i) => (
                  <div key={i} className="shrink-0 rounded-lg overflow-hidden"
                       style={{ background: PANEL_BG, border: `1px solid ${PANEL_BORDER}`, minWidth: detectionFrames[i] ? 140 : 128 }}>
                    {detectionFrames[i] && (
                      <img
                        src={`data:image/jpeg;base64,${detectionFrames[i]}`}
                        alt={d.object_class}
                        className="w-full object-cover"
                        style={{ height: 80 }}
                      />
                    )}
                    <div className="p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-sm capitalize" style={{ color: "#d4d820" }}>{d.object_class}</span>
                        <span className="text-xs font-mono" style={{ color: "#6b8a60" }}>{(d.confidence * 100).toFixed(0)}%</span>
                      </div>
                      <div className="text-xs font-mono leading-relaxed" style={{ color: "#5a7252" }}>
                        N {d.north.toFixed(2)}<br />E {d.east.toFixed(2)}
                      </div>
                      <div className="text-xs mt-1" style={{ color: "#3a4e34" }}>
                        {new Date(d.timestamp * 1000).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </section>

    </div>
  );
}
