import { useTelemetryStream } from "../hooks/useTelemetryStream";

export default function TelemetryBox() {
  const { telem, status } = useTelemetryStream();

  const bat = telem.battery_pct;
  const batColor = bat <= 0 ? "text-zinc-500"
    : bat < 20 ? "text-red-400"
    : bat < 40 ? "text-yellow-400"
    : "text-green-400";

  return (
    <div className="text-sm space-y-1.5 font-mono">

      {/* FC connection */}
      <div className="flex justify-between">
        <span className="text-zinc-500">FC Link</span>
        <span className={telem.connected ? "text-green-400" : "text-red-400"}>
          {telem.connected ? "CONNECTED" : "OFFLINE"}
        </span>
      </div>

      {/* WS status */}
      <div className="flex justify-between">
        <span className="text-zinc-500">WS</span>
        <span className={status === "live" ? "text-green-400" : "text-yellow-400"}>
          {status.toUpperCase()}
        </span>
      </div>

      <hr className="border-zinc-700" />

      <div className="flex justify-between">
        <span className="text-zinc-500">State</span>
        <span className="text-cyan-300">{telem.state}</span>
      </div>

      <div className="flex justify-between">
        <span className="text-zinc-500">Mode</span>
        <span className="text-zinc-200">{telem.flight_mode}</span>
      </div>

      <div className="flex justify-between">
        <span className="text-zinc-500">Armed</span>
        <span className={telem.armed ? "text-red-400 font-bold" : "text-zinc-400"}>
          {telem.armed ? "ARMED" : "DISARMED"}
        </span>
      </div>

      <hr className="border-zinc-700" />

      <div className="flex justify-between">
        <span className="text-zinc-500">Altitude</span>
        <span className="text-zinc-200">{telem.rel_alt.toFixed(2)} m</span>
      </div>

      <div className="flex justify-between">
        <span className="text-zinc-500">Heading</span>
        <span className="text-zinc-200">{telem.heading_deg.toFixed(1)}°</span>
      </div>

      <div className="flex justify-between">
        <span className="text-zinc-500">NED</span>
        <span className="text-zinc-200">
          {telem.local_north.toFixed(2)} / {telem.local_east.toFixed(2)} / {telem.local_down.toFixed(2)}
        </span>
      </div>

      <div className="flex justify-between">
        <span className="text-zinc-500">Battery</span>
        <span className={batColor}>
          {bat <= 0 ? "N/A" : `${bat.toFixed(0)}%`}
        </span>
      </div>

    </div>
  );
}
