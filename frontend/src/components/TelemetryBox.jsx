import { useTelemetryStream } from "../hooks/useTelemetryStream";

export default function TelemetryBox() {
  const { telem, status } = useTelemetryStream();

  const bat = telem.battery_pct;
  const batColor = bat <= 0  ? "#3a4e34"
    : bat < 20               ? "#f87171"
    : bat < 40               ? "#fbbf24"
    :                          "#4ade80";

  function Row({ label, value, color }) {
    return (
      <div className="flex justify-between items-center">
        <span className="stat-label">{label}</span>
        <span className="text-sm font-mono" style={{ color: color || "#d0dcc8" }}>{value}</span>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">

      <Row label="FC Link"
        value={telem.connected ? "Connected" : "Offline"}
        color={telem.connected ? "#4ade80" : "#f87171"} />
      <Row label="Telemetry"
        value={status.toUpperCase()}
        color={status === "live" ? "#4ade80" : "#fbbf24"} />

      <div style={{ borderTop: "1px solid rgba(242,235,215,0.1)", margin: "4px 0" }} />

      <Row label="State"    value={telem.state}       color="#d4d820" />
      <Row label="Mode"     value={telem.flight_mode} />
      <Row label="Armed"
        value={telem.armed ? "Armed" : "Disarmed"}
        color={telem.armed ? "#f87171" : "#3a4e34"} />

      <div style={{ borderTop: "1px solid rgba(242,235,215,0.1)", margin: "4px 0" }} />

      <Row label="Altitude" value={`${telem.rel_alt.toFixed(2)} m`} />
      <Row label="Heading"  value={`${telem.heading_deg.toFixed(1)}°`} />

      <div>
        <span className="stat-label block mb-1.5">NED Position</span>
        <div className="grid grid-cols-3 gap-1 text-xs font-mono" style={{ color: "#6b8a60" }}>
          {[["N", telem.local_north], ["E", telem.local_east], ["D", telem.local_down]].map(([ax, val]) => (
            <div key={ax} className="rounded px-2 py-1" style={{ background: "rgba(242,235,215,0.04)", border: "1px solid rgba(242,235,215,0.1)" }}>
              <span style={{ color: "#3a4e34" }}>{ax} </span>{val.toFixed(2)}
            </div>
          ))}
        </div>
      </div>

      <Row label="Battery"
        value={bat <= 0 ? "N/A" : `${bat.toFixed(0)}%`}
        color={batColor} />

    </div>
  );
}
