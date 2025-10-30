import { useLidarStream } from "./hooks/useLidarStream";
import LidarCanvas from "./components/LidarCanvas";

export default function App() {
  const { points, status } = useLidarStream();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <h1 className="text-3xl font-bold mb-4">PiDrone LiDAR Live</h1>
      <div className="flex gap-6">
        <LidarCanvas points={points} />
        <div className="space-y-4">
          <div className={`text-sm ${status === "live" ? "text-green-400" : "text-red-400"}`}>
            {status}
          </div>
          <div>Points/frame: {points.length}</div>
        </div>
      </div>
    </div>
  );
}
