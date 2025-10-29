from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio, json
from lidar_test.lidar_streamer import LidarStreamer

app = FastAPI()

# === STATIC FILES SETUP (FIXED) ===
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "app" / "static"

print("Static directory path:", STATIC_DIR)

if not STATIC_DIR.exists():
    raise RuntimeError(f"Static directory not found: {STATIC_DIR}")

# Only mount once — absolute path only
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# === LiDAR setup ===
lidar = LidarStreamer(max_points=3000)

latest_command = {"command": None}


@app.on_event("startup")
def startup():
    lidar.start()


@app.on_event("shutdown")
def shutdown():
    lidar.stop()


@app.get("/")
def serve_frontend():
    # Serve index.html from the static directory
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/command")
async def receive_command(request: Request):
    data = await request.json()
    command = data.get("command", "")
    latest_command["command"] = command
    print(f"Received command: {command}")
    return JSONResponse({"message": f"Command '{command}' received"})


@app.get("/api/latest")
def get_latest():
    return JSONResponse({"command": latest_command["command"]})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/lidar")
async def lidar_ws(ws: WebSocket):
    await ws.accept()
    try:
        send_interval = 0.1  # ~10 FPS
        while True:
            xs, ys, cs = lidar.snapshot(max_out=1500)
            payload = json.dumps({"x": xs, "y": ys, "c": cs})
            await ws.send_text(payload)
            await asyncio.sleep(send_interval)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("WebSocket error:", e)
        pass