import { useState } from "react";

export default function AICamFeed() {
  const [status, setStatus] = useState("loading"); // loading | ok | error

  return (
    <div className="flex flex-col items-center justify-center w-full h-full gap-2">
      {status === "error" && (
        <div className="text-center">
          <p className="text-xs mb-2" style={{ color: "#f87171" }}>Camera stream unavailable</p>
          <button
            className="text-xs px-3 py-1 rounded"
            style={{ background: "rgba(242,235,215,0.07)", color: "#c8d8c0", border: "1px solid rgba(242,235,215,0.13)" }}
            onClick={() => setStatus("loading")}
          >Retry</button>
        </div>
      )}
      <img
        src="/camera/stream"
        alt="AI Camera Live Feed"
        className="rounded-lg object-contain"
        style={{
          maxWidth: "100%", maxHeight: "100%",
          display: status === "error" ? "none" : "block",
        }}
        onLoad={() => setStatus("ok")}
        onError={() => setStatus("error")}
      />
    </div>
  );
}
