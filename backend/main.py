import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.lidar_streamer import LidarStreamer
from backend.app.camera_streamer import router as camera_router

SIM_MODE = os.getenv("SIM_MODE", "true").lower() != "false"
print(f"[main] SIM_MODE={SIM_MODE}")

app = FastAPI()
app.include_router(camera_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Static files ===
BASE_DIR   = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "app" / "static"

if not STATIC_DIR.exists():
    raise RuntimeError(f"Static directory not found: {STATIC_DIR}")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

# === LiDAR (always on) ===
lidar = LidarStreamer(max_points=3000)

# === Drone controller (hardware only) ===
if not SIM_MODE:
    from backend.drone.controller import DroneController
    from backend.drone.state_machine import StateMachine
    from backend.drone.router import router as drone_router, ws_router, set_dependencies, get_singletons
    from backend.drone.demo_router import router as demo_router, set_demo_dependencies
    from backend.app.servo_gripper import ServoGripper

    ctrl    = DroneController()
    sm      = StateMachine()
    gripper = ServoGripper()
    set_dependencies(ctrl, sm, lidar, gripper)
    _log, _grid = get_singletons()
    set_demo_dependencies(sm, _log, _grid, lidar, gripper)
    app.include_router(drone_router)
    app.include_router(ws_router)
    app.include_router(demo_router)


@app.on_event("startup")
async def startup():
    lidar.start()
    if not SIM_MODE:
        asyncio.create_task(_connect_drone())


async def _connect_drone():
    try:
        await ctrl.connect(timeout=30.0)
        print("[main] DroneController connected ✓")
    except Exception as e:
        print(f"[main] DroneController connection failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    lidar.stop()
    if not SIM_MODE:
        await ctrl.disconnect()
        gripper.shutdown()


@app.get("/")
def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "sim_mode": SIM_MODE}


@app.websocket("/ws/lidar")
async def lidar_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            xs, ys, cs, nearest = lidar.snapshot(max_out=1500)
            too_close = nearest is not None and nearest < 0.05
            payload = json.dumps({
                "x": xs,
                "y": ys,
                "c": cs,
                "nearest_distance": nearest,
                "too_close": too_close,
            })
            await ws.send_text(payload)
            if too_close:
                print(f"[ALERT] Object too close: {nearest*100:.1f} cm")
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("[lidar_ws] error:", e)
