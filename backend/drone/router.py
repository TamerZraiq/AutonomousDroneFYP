"""
Drone router — step 1 (hardware bringup).

Exposes:
  GET  /api/drone/status    — one-shot telemetry snapshot + SM state
  WS   /ws/telemetry        — 5 Hz stream of telemetry snapshot

More endpoints (arm, takeoff, offboard, tasks…) will be added in later steps.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .controller import DroneController
from .state_machine import StateMachine

router    = APIRouter(prefix="/api/drone")  # REST endpoints
ws_router = APIRouter()                     # WebSocket endpoints (no prefix)

# Singletons injected by main.py via set_controller()
_ctrl: DroneController | None = None
_sm: StateMachine | None = None


def set_controller(ctrl: DroneController, sm: StateMachine):
    global _ctrl, _sm
    _ctrl = ctrl
    _sm = sm


# ── REST ──────────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    if _ctrl is None:
        return {"error": "controller not initialised"}
    snap = _ctrl.snapshot()
    return {
        "state":       _sm.state if _sm else "UNKNOWN",
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


# ── WebSocket telemetry ───────────────────────────────────────────────────────

@ws_router.websocket("/ws/telemetry")
async def telemetry_ws(ws: WebSocket):
    await ws.accept()
    try:
        async for snap in _ctrl.stream_telemetry(hz=5.0):
            payload = json.dumps({
                "connected":   snap.connected,
                "state":       _sm.state if _sm else "UNKNOWN",
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
                # placeholders — filled in later steps
                "mission":  {"active": False, "current_wp": 0, "total_wp": 0, "finished": False},
                "offboard": {"active": False, "paused": False, "current_wp": 0, "total_wp": 0, "finished": False},
                "detections": [],
            })
            await ws.send_text(payload)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("[telemetry_ws] error:", e)
