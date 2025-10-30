import { useLidarStream } from "./hooks/useLidarStream";
import LidarCanvas from "./components/LidarCanvas";
import DashboardCard from "./components/DashboardCard";
import AICamFeed from "./components/AICamFeed";
import TelemetryBox from "./components/TelemetryBox";
import "./index.css";

export default function App() {
  const { points, status } = useLidarStream();

  return (
    <div className="min-h-screen bg-gradient-to-br from-black via-zinc-950 to-zinc-900 text-zinc-100 grid grid-cols-1 md:grid-cols-2 gap-8 p-10">
      
      {/* LEFT PANEL */}
      <section className="flex flex-col justify-center space-y-6">
        <h1 className="text-4xl font-bold tracking-tight">
          <span className="text-cyan-400">AeroDrop</span> Dashboard
        </h1>
        <p className="text-zinc-400 leading-relaxed max-w-md">
          Multi-sensor autonomous drone system integrating LiDAR mapping,
          onboard AI vision, and distributed telemetry. This dashboard provides
          real-time visualization of sensor feeds and system status.
        </p>
        <div>
          <span className="text-sm text-zinc-500">Status:</span>{" "}
          <span className={status === "live" ? "text-green-400" : "text-red-400"}>
            {status.toUpperCase()}
          </span>
        </div>
      </section>

      {/* RIGHT PANEL */}
      <section className="flex flex-col gap-8">
        <DashboardCard title="LiDAR Mapping">
          <LidarCanvas points={points} />
        </DashboardCard>

        <DashboardCard title="AI Camera">
          <AICamFeed />
        </DashboardCard>

        <DashboardCard title="Telemetry">
          <TelemetryBox />
        </DashboardCard>
      </section>
    </div>
  );
}
