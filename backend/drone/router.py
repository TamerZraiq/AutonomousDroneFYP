"""
Drone router — all REST endpoints + WebSocket streams.

REST
----
GET  /api/drone/status
POST /api/drone/arm
POST /api/drone/takeoff        body: {alt: float}
POST /api/drone/land
POST /api/drone/rtl
POST /api/drone/emergency
POST /api/drone/reset
POST /api/drone/task/start     body: {target, row_length, rows, altitude}
POST /api/drone/task/cancel
POST /api/drone/task/pause
POST /api/drone/task/resume
POST /api/drone/detections/clear
GET  /api/drone/report/json

WebSockets (no /api prefix)
---------------------------
WS /ws/telemetry   5 Hz  full drone state
WS /ws/map         2 Hz  occupancy grid
"""

import asyncio
import json
import base64

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .controller import DroneController
from .state_machine import StateMachine, State
from .task_executor import TaskExecutor
from backend.app.detection_log import DetectionLog
from backend.app.occupancy_grid import OccupancyGrid
from backend.app.lidar_streamer import LidarStreamer

router    = APIRouter(prefix="/api/drone")
ws_router = APIRouter()

# ── singletons injected by main.py ───────────────────────────────────────────
_ctrl:   DroneController | None = None
_sm:     StateMachine    | None = None
_lidar:  LidarStreamer   | None = None
_log:    DetectionLog    | None = None
_grid:   OccupancyGrid   | None = None
_task_exec: TaskExecutor | None = None


def set_dependencies(
    ctrl:  DroneController,
    sm:    StateMachine,
    lidar: LidarStreamer,
):
    global _ctrl, _sm, _lidar, _log, _grid, _task_exec
    _ctrl  = ctrl
    _sm    = sm
    _lidar = lidar
    _log   = DetectionLog()
    _grid  = OccupancyGrid()
    _task_exec = TaskExecutor(ctrl, lidar, _log, _grid)


# ── helpers ───────────────────────────────────────────────────────────────────

def _snap_dict():
    snap = _ctrl.snapshot()
    return {
        "state":       _sm.state,
        "connected":   snap.connected,
        "armed":       snap.armed,
        "flight_mode": snap.flight_mode,
        "lat":         snap.lat,
        "lon":         snap.lon,
        "abs_alt":     snap.abs_alt,
        "rel_alt":     snap.rel_alt,
        "battery_pct": snap.battery_pct,
        "local_north": snap.local_north,
        "local_east":  snap.local_east,
        "local_down":  snap.local_down,
        "heading_deg": snap.heading_deg,
    }


# ── REST: status ──────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    if _ctrl is None:
        return JSONResponse({"error": "not initialised"}, status_code=503)
    d = _snap_dict()
    os = _task_exec.offboard_status
    d["offboard"] = {
        "active": os.active, "paused": os.paused,
        "current_wp": os.current_wp, "total_wp": os.total_wp,
        "finished": os.finished, "blocked": os.blocked,
    }
    d["detections"] = _log.as_dicts()
    return d


# ── REST: flight commands ─────────────────────────────────────────────────────

@router.post("/arm")
async def arm():
    if not await _sm.transition(State.ARMED):
        return JSONResponse({"error": f"cannot arm from {_sm.state}"}, status_code=409)
    try:
        await _ctrl.arm()
        return {"ok": True, "state": _sm.state}
    except Exception as e:
        await _sm.transition(State.IDLE)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/takeoff")
async def takeoff(body: dict = {}):
    alt = float(body.get("alt", 1.2))
    if not await _sm.transition(State.TAKEOFF):
        return JSONResponse({"error": f"cannot takeoff from {_sm.state}"}, status_code=409)
    try:
        await _ctrl.takeoff(alt)
        return {"ok": True, "state": _sm.state, "alt": alt}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/land")
async def land():
    try:
        await _ctrl.land()
        await _sm.transition(State.LANDED)
        return {"ok": True, "state": _sm.state}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/rtl")
async def rtl():
    if not await _sm.transition(State.RTL):
        return JSONResponse({"error": f"cannot RTL from {_sm.state}"}, status_code=409)
    try:
        await _ctrl.rtl()
        return {"ok": True, "state": _sm.state}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/emergency")
async def emergency():
    await _sm.trigger_emergency()
    _task_exec.cancel()
    try:
        await _ctrl.land()
    except Exception:
        pass
    return {"ok": True, "state": _sm.state}


@router.post("/reset")
async def reset():
    if _sm.state not in (State.LANDED, State.EMERGENCY, State.ARMED):
        return JSONResponse({"error": f"cannot reset from {_sm.state}"}, status_code=409)
    await _sm.transition(State.IDLE)
    return {"ok": True, "state": _sm.state}


# ── REST: mission ─────────────────────────────────────────────────────────────

@router.post("/task/start")
async def task_start(body: dict):
    """
    body: {
        "target":     "person",   # what camera looks for
        "row_length": 3.0,        # metres per sweep row
        "rows":       4,          # number of rows
        "altitude":   1.2         # cruise altitude metres
    }
    """
    if not _sm.is_airborne():
        return JSONResponse({"error": "must be airborne to start task"}, status_code=409)
    if not await _sm.transition(State.MISSION):
        return JSONResponse({"error": f"cannot start mission from {_sm.state}"}, status_code=409)

    _log.clear()
    _grid.reset()

    await _task_exec.start(
        target=body.get("target", "person"),
        row_length=float(body.get("row_length", 3.0)),
        rows=int(body.get("rows", 4)),
        altitude=float(body.get("altitude", 1.2)),
    )

    # Watch for mission completion → auto RTL
    asyncio.create_task(_watch_mission_end())
    return {"ok": True, "state": _sm.state}


async def _watch_mission_end():
    while True:
        await asyncio.sleep(1.0)
        os = _task_exec.offboard_status
        if not os.active and os.finished:
            await _sm.transition(State.RTL)
            try:
                await _ctrl.rtl()
            except Exception:
                pass
            break


@router.post("/task/cancel")
async def task_cancel():
    _task_exec.cancel()
    return {"ok": True}


@router.post("/task/pause")
async def task_pause():
    _task_exec.pause()
    return {"ok": True}


@router.post("/task/resume")
async def task_resume():
    _task_exec.resume()
    return {"ok": True}


@router.post("/detections/clear")
async def clear_detections():
    _log.clear()
    _grid.reset()
    return {"ok": True}


# ── REST: report ──────────────────────────────────────────────────────────────

@router.get("/report/json")
def report_json():
    entries = _log.all()
    out = []
    for e in entries:
        d = {
            "object_class": e.object_class,
            "confidence":   round(e.confidence, 3),
            "north":        round(e.north, 3),
            "east":         round(e.east, 3),
            "timestamp":    e.timestamp,
        }
        if e.frame_jpg:
            d["frame_b64"] = base64.b64encode(e.frame_jpg).decode()
        out.append(d)
    return {"detections": out, "total": len(out)}


# ── WebSocket: telemetry (5 Hz) ───────────────────────────────────────────────

@ws_router.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket):
    await ws.accept()
    try:
        async for snap in _ctrl.stream_telemetry(hz=5.0):
            os = _task_exec.offboard_status
            payload = json.dumps({
                "connected":   snap.connected,
                "state":       _sm.state,
                "armed":       snap.armed,
                "flight_mode": snap.flight_mode,
                "lat":         snap.lat,
                "lon":         snap.lon,
                "abs_alt":     snap.abs_alt,
                "rel_alt":     snap.rel_alt,
                "battery_pct": snap.battery_pct,
                "local_north": snap.local_north,
                "local_east":  snap.local_east,
                "local_down":  snap.local_down,
                "heading_deg": snap.heading_deg,
                "offboard": {
                    "active":     os.active,
                    "paused":     os.paused,
                    "current_wp": os.current_wp,
                    "total_wp":   os.total_wp,
                    "finished":   os.finished,
                    "blocked":    os.blocked,
                },
                "detections": _log.as_dicts(),
            })
            await ws.send_text(payload)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("[telemetry_ws] error:", e)


# ── WebSocket: map (2 Hz) ─────────────────────────────────────────────────────

@ws_router.websocket("/ws/map")
async def map_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = json.dumps(_grid.serialise())
            await ws.send_text(payload)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("[map_ws] error:", e)
