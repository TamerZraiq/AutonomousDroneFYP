"""
Demo router — run real sensors (LiDAR + camera AI) without flying.

POST /api/demo/state/{state_name}   Force state machine to any state (+ realistic telemetry overrides)
POST /api/demo/scan/start           Start live LiDAR mapping + camera AI detection
POST /api/demo/scan/stop            Stop live scan
GET  /api/demo/scan/status          Whether scan is running
POST /api/demo/capture              Manually log current camera frame as a detection
"""

import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .state_machine import StateMachine, State
from backend.app.detection_log import DetectionLog
from backend.app.occupancy_grid import OccupancyGrid
from backend.app.lidar_streamer import LidarStreamer

router = APIRouter(prefix="/api/demo")

_sm:    StateMachine | None = None
_log:   DetectionLog | None = None
_grid:  OccupancyGrid | None = None
_lidar: LidarStreamer | None = None

_scan_task: asyncio.Task | None = None

# Realistic fake FC telemetry per state, applied on top of real FC snapshot
# so the UI looks convincing even when FC is offline
_STATE_OVERRIDES: dict[State, dict] = {
    State.IDLE:      {"connected": True, "armed": False, "flight_mode": "STABILIZE", "rel_alt": 0.0},
    State.ARMED:     {"connected": True, "armed": True,  "flight_mode": "STABILIZE", "rel_alt": 0.0},
    State.TAKEOFF:   {"connected": True, "armed": True,  "flight_mode": "GUIDED",    "rel_alt": 1.1},
    State.MISSION:   {"connected": True, "armed": True,  "flight_mode": "GUIDED",    "rel_alt": 1.2},
    State.RTL:       {"connected": True, "armed": True,  "flight_mode": "RTL",       "rel_alt": 0.6},
    State.LANDED:    {"connected": True, "armed": False, "flight_mode": "STABILIZE", "rel_alt": 0.0},
    State.EMERGENCY: {"connected": True, "armed": False, "flight_mode": "STABILIZE", "rel_alt": 0.0},
}

_demo_overrides: dict = {}


def get_demo_overrides() -> dict:
    """Called by router.py telemetry WS to merge fake FC values into the payload."""
    return _demo_overrides


def set_demo_dependencies(
    sm:    StateMachine,
    log:   DetectionLog,
    grid:  OccupancyGrid,
    lidar: LidarStreamer,
):
    global _sm, _log, _grid, _lidar
    _sm    = sm
    _log   = log
    _grid  = grid
    _lidar = lidar


# ── background scan ───────────────────────────────────────────────────────────

async def _live_scan(target_class: str):
    """
    Feeds real LiDAR into the occupancy grid and logs real camera AI detections.
    Drone treated as stationary at NED origin (0, 0), heading 0.
    Mirrors _monitor_detections + _update_map from TaskExecutor but no flight needed.
    """
    from backend.app import camera_streamer
    last_det_ts = 0.0

    print(f"[Demo] _live_scan started, target={target_class!r}", flush=True)
    last_logged: dict[str, float] = {}
    COOLDOWN = 5.0  # seconds between logged detections of the same class
    while True:
        await asyncio.sleep(0.2)

        # Real LiDAR → occupancy grid
        xs, ys, _, _ = _lidar.snapshot(max_out=500)
        if xs:
            _grid.update(0.0, 0.0, 0.0, list(zip(xs, ys)))

        # Real camera AI → detection log
        det = camera_streamer.latest_detection
        if not det or not det.get("objects"):
            continue
        ts = det.get("timestamp", 0)
        if ts == last_det_ts:
            continue
        last_det_ts = ts

        for obj in det["objects"]:
            label = str(obj.get("class", obj.get("label", ""))).lower()
            conf  = float(obj.get("score", obj.get("confidence", 0.0)))
            if target_class in label and conf > 0.5:
                now = time.time()
                if now - last_logged.get(label, 0) < COOLDOWN:
                    continue
                last_logged[label] = now
                with camera_streamer._frame_lock:
                    frame = camera_streamer.latest_frame
                _log.add(label, conf, 0.0, 0.0, frame_jpg=frame)
                _grid.add_detection(0.0, 0.0)
                print(f"[Demo] AI detection: {label} {conf:.2f}")


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/state/{state_name}")
async def force_state(state_name: str):
    """Force the state machine to any state and apply matching fake FC telemetry."""
    global _demo_overrides
    try:
        s = State(state_name.upper())
    except ValueError:
        return JSONResponse(
            {"error": f"unknown state '{state_name}'", "valid": [e.value for e in State]},
            status_code=400,
        )
    async with _sm._lock:
        _sm._state = s
    _demo_overrides = dict(_STATE_OVERRIDES.get(s, {}))
    return {"ok": True, "state": _sm.state, "overrides": _demo_overrides}


@router.post("/scan/start")
async def scan_start(body: dict = {}):
    """Start live LiDAR mapping + camera AI detection (no flight required)."""
    global _scan_task
    if _scan_task and not _scan_task.done():
        return {"ok": True, "running": True, "message": "already running"}
    _grid.reset()
    target = body.get("target", "person").lower()

    _scan_task = asyncio.create_task(_live_scan(target))
    return {"ok": True, "running": True, "target": target}


@router.post("/scan/stop")
async def scan_stop():
    """Stop the live scan."""
    global _scan_task
    if _scan_task and not _scan_task.done():
        _scan_task.cancel()
    _scan_task = None
    return {"ok": True, "running": False}


@router.get("/scan/status")
async def scan_status():
    running = _scan_task is not None and not _scan_task.done()
    return {"running": running}


@router.post("/capture")
async def capture_detection(body: dict = {}):
    """
    Manually log the current camera frame as a person detection.
    Use this when the AI threshold isn't being met but the camera sees someone.
    """
    from backend.app import camera_streamer
    obj_class  = body.get("class", "person")
    confidence = float(body.get("confidence", 0.95))
    north      = float(body.get("north", 0.0))
    east       = float(body.get("east", 0.0))
    with camera_streamer._frame_lock:
        frame = camera_streamer.latest_frame
    if frame is None:
        return JSONResponse({"error": "no camera frame available yet"}, status_code=503)
    _log.add(obj_class, confidence, north, east, frame_jpg=frame)
    _grid.add_detection(north, east)
    print(f"[Demo] Manual capture: {obj_class} {confidence:.2f}")
    return {"ok": True, "total": len(_log), "has_frame": True}
