# PiDrone Dev Log

Running log of issues encountered, fixes applied, and outcomes.

---

## Session 1 — 2026-03-25

### Issue: Website status shows "DISCONNECTED", LiDAR not working

**Symptoms**
- Dashboard status badge showed `DISCONNECTED` in red
- LiDAR canvas received no data
- Camera feed was working fine
- Browser Network tab showed two pending WebSocket connections to `/ws/lidar` with no status code

**Root Causes Found**

1. **Duplicate `@app.websocket` decorator** (`backend/main.py:75-76`)
   - The `/ws/lidar` route was registered twice with `@app.websocket("/ws/lidar")` stacked on the same function
   - FastAPI silently drops one, which can corrupt route registration
   - **Fix:** Removed the duplicate decorator

2. **`nearest` not exported from `useLidarStream` hook** (`frontend/src/hooks/useLidarStream.js`)
   - `App.jsx` destructured `{ points, nearest, status }` but the hook only returned `{ points, status }`
   - `nearest` was always `undefined`, so the LiDAR canvas telemetry bar showed `--` for nearest distance
   - **Fix:** Added `nearest` state, set it from `data.nearest_distance` in the `onmessage` handler, and included it in the return value

3. **WebSocket connecting to wrong host** — primary cause of disconnect
   - Camera URL was hardcoded to `http://172.20.10.2:8000/camera/stream`
   - WebSocket used `location.hostname` dynamically — if the browser accessed the site via any other hostname/IP, the WebSocket targeted the wrong host
   - Confirmed: `curl` WebSocket handshake from the Pi directly to `172.20.10.2:8000/ws/lidar` returned `101 Switching Protocols` and streamed data correctly, proving the backend was fine
   - **Fix:** Added Vite dev server proxy in `vite.config.js` to forward `/ws/*` → `ws://172.20.10.2:8000` and `/camera/*` → `http://172.20.10.2:8000`. Updated hook to use `location.host` (relative) instead of hardcoded port 8000. Updated camera URL to relative path `/camera/stream`

**What Didn't Work**
- Restarting uvicorn alone did not fix the disconnect (backend was already healthy)
- The duplicate route fix alone was not sufficient — the hostname mismatch was the main blocker

**What Worked**
- Vite proxy approach cleanly decouples frontend from backend IP, works regardless of how the site is accessed
- `curl` WebSocket handshake test was useful to isolate whether the issue was backend or frontend/network

**Files Changed**
- `backend/main.py` — removed duplicate `@app.websocket("/ws/lidar")`
- `frontend/src/hooks/useLidarStream.js` — added `nearest` state + export, changed WS URL to use `location.host`
- `frontend/src/components/AICamFeed.jsx` — changed camera URL to relative path
- `frontend/vite.config.js` — added proxy for `/ws` and `/camera`

---

## Session 1 continued — Hardware Bringup Step 1: FC ↔ RPi pipeline

### Goal
Get `backend/drone/` module onto the RPi, confirm the backend can connect to the H7A3 FC via MAVProxy, and show live telemetry on the website.

### Dependencies installed (into `venv/`)
- `pymavlink==2.4.49` — MAVLink connection for NED setpoints
- `mavsdk==3.15.3` — high-level FC control (arm, takeoff, land, telemetry subscriptions)
- `MAVProxy==1.8.74` — serial→UDP bridge
- `future==1.0.0` — missing MAVProxy dependency (was not pulled in automatically)

**Error encountered:** MAVProxy crashed on first run with `ModuleNotFoundError: No module named 'future'`
**Fix:** `pip install future`

### Files created
- `backend/drone/__init__.py`
- `backend/drone/state_machine.py` — 7-state FSM (IDLE/ARMED/TAKEOFF/MISSION/RTL/LANDED/EMERGENCY)
- `backend/drone/controller.py` — MAVSDK + pymavlink wrapper; 7 background tasks keeping `TelemetrySnapshot` current; `connect()`, `arm()`, `takeoff()`, `land()`, `rtl()`, `send_ned_setpoint()`
- `backend/drone/router.py` — `/api/drone/status` REST endpoint + `/ws/telemetry` WebSocket (5 Hz); uses separate `ws_router` (no prefix) to avoid `/api/drone/ws/telemetry` path bug
- `backend/drone/test_hitl.py` — smoke-test: connects MAVSDK, prints health + telemetry, exits
- `frontend/src/hooks/useTelemetryStream.js` — WS hook with 3 s auto-reconnect and 6 s stale watchdog
- `frontend/src/components/TelemetryBox.jsx` — replaced placeholder with live FC Link, WS status, state, mode, armed, altitude, heading, NED, battery

### `backend/main.py` updated
- Reads `SIM_MODE` env var (`true` by default — safe fallback)
- When `SIM_MODE=false`: imports `DroneController`/`StateMachine`/routers, registers them, spawns `_connect_drone()` background task on startup

### Bug fixed during development
`controller.py` originally had heading poll inside `_poll_local_position()` after the first `async for` loop — it would never run since the first generator never ends. Split into separate `_poll_heading()` task.

### Smoke-test result (confirmed working)
```
✓ Connected!
  is_armable=False  local_pos_ok=False  global_pos_ok=False
  lat=0.000000  lon=0.000000  alt=-0.82 m
  battery=-1.0%
  flight_mode=STABILIZED
✓ Smoke-test passed
```
- `is_armable=False`, `local_pos_ok=False` — expected, optical flow + ToF not yet wired
- `battery=-1.0%` — expected, `BATT_MONITOR=0` on H7A3 (not configured)
- `lat/lon=0` — expected, GPS disabled for indoor flight

### MAVProxy command (current)
```bash
mavproxy.py --master=/dev/ttyAMA2 --baudrate=115200 \
    --out=udpout:0.0.0.0:14552 \
    --out=udpout:0.0.0.0:14553 \
    --daemon
```
To also connect Mission Planner from laptop, add `--out=udpout:<laptop-ip>:14550`.

### Backend hardware startup
```bash
cd ~/pidrone && source venv/bin/activate
export SIM_MODE=false
export MAVSDK_CONNECTION="udpin://0.0.0.0:14552"
export GUIDED_PORT=14553
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Next
- Confirm website TelemetryBox shows live FC data (flight mode, armed, heading)
- Step 2: occupancy map building from real LD06 data

---

## Session 1 continued — Frontend Serving, Static Asset Fix & Live Telemetry Confirmed

### Goal
Get the React dashboard loading on the browser and confirm live FC telemetry renders on the website.

---

### Problem 1: Vite Dev Server Hanging on Pi (blank white page, 0 bytes in 12+ seconds)

**Root cause — architectural:**
Vite dev server does on-demand module transformation. On first page load, every `import` in the React tree gets intercepted by Vite, transpiled from JSX/ESM, and sent to the browser one by one. On a development machine this is fast. On the Pi, which was simultaneously running:
- MAVProxy consuming ~20% CPU continuously (parsing 230400 baud serial frames)
- uvicorn + MAVSDK + mavsdk_server gRPC subprocess
- VS Code Remote SSH server + extension host (~1.3 GB RAM across VS Code processes alone)
- TypeScript language server

...the first Vite request accepted the TCP connection but the HTTP response never arrived in time. The browser received 0 bytes and timed out after 12.29 seconds. No console errors appeared because the JS bundle never loaded — React never ran at all.

**Additional factor — VS Code port forwarding:**
The user accesses the Pi via VS Code Remote SSH. VS Code tunnels ports from the Pi to `localhost` on the laptop. When accessing `localhost:5173`, every HTTP request travels: laptop browser → VS Code tunnel → Pi `127.0.0.1:5173`. This adds latency on top of Vite's already slow transformation. Direct IP access (`172.20.10.2:5173`) bypassed the tunnel but hit the same underlying Vite hang — 0 bytes, 12 seconds timeout — confirming the issue was Vite's transformation latency, not the tunnel itself.

**Decision: build for production, serve from FastAPI**
Running a Vite dev server permanently on a Pi whose primary job is real-time drone control is the wrong architecture. Instead:
- `npm run build` runs Vite's Rollup bundler once, producing optimised static assets (minified, tree-shaken, gzip ~64 KB)
- Output is copied into `backend/app/static/`
- FastAPI serves everything from port 8000 — no Node.js process running at runtime
- Result: 200 OK for the HTML document in **31 ms**

**Build output:**
```
dist/index.html                   0.46 kB │ gzip:  0.29 kB
dist/assets/index-Nz8COY9l.css    9.28 kB │ gzip:  2.60 kB
dist/assets/index-B06Ry2pG.js   203.34 kB │ gzip: 63.74 kB
built in 5.75s
```

**Workflow going forward:**
- Active frontend development: run `npm run dev -- --host 0.0.0.0` temporarily on the Pi (or on the laptop if proxied)
- Deploying changes: `npm run build && cp -r dist/* ../backend/app/static/`
- Runtime: Vite is completely off; browser hits `http://172.20.10.2:8000`

---

### Problem 2: JS and CSS returning 404 after build copy

**Root cause — FastAPI static mount path mismatch:**
Vite builds assets with hashed filenames into a subdirectory: `dist/assets/index-B06Ry2pG.js`. The `index.html` it generates references them with absolute root paths: `<script src="/assets/index-B06Ry2pG.js">`.

FastAPI was configured to mount the static directory at `/static`:
```python
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```
This means `/static/assets/index-B06Ry2pG.js` would resolve, but Vite's HTML asks for `/assets/index-B06Ry2pG.js` — a 404.

**Fix:**
Added a second mount specifically for the assets subdirectory at `/assets`:
```python
app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
```
FastAPI now serves:
- `/` → `index.html` (via `FileResponse`)
- `/static/*` → static directory (CSS, images, etc. if any)
- `/assets/*` → Vite's hashed JS and CSS bundles

After this fix: JS loaded (200, 13 ms), CSS loaded (200, 10 ms), React mounted, dashboard rendered.

---

### Result: Full End-to-End FC → RPi → Website Telemetry Pipeline Confirmed Working

**Verified live in browser (`http://172.20.10.2:8000`):**

| Field | Value observed |
|-------|---------------|
| FC Link | CONNECTED |
| WS | LIVE |
| State | IDLE |
| Mode | STABILIZED |
| Armed | DISARMED |
| Heading | 24.15° (real IMU heading) |
| Altitude | ~0.10 m (barometric, bench reading) |
| NED | 0.0 / 0.0 / 0.0 |
| Battery | N/A (`BATT_MONITOR=0`) |

**Data path confirmed:**
```
H7A3 FC (ArduCopter V4.6.3)
  │  UART @ /dev/ttyAMA2, 115200 baud
  ▼
MAVProxy daemon
  │  UDP 14552 → MAVSDK (telemetry subscriptions, async generators)
  │  UDP 14553 → pymavlink (NED setpoint channel, reserved)
  ▼
DroneController (7 background asyncio tasks)
  → _poll_connection, _poll_armed, _poll_flight_mode,
    _poll_position, _poll_battery, _poll_local_position, _poll_heading
  │  All writing into TelemetrySnapshot dataclass under asyncio.Lock
  ▼
/ws/telemetry WebSocket (5 Hz, FastAPI)
  │  JSON payload: connected, state, armed, flight_mode, lat, lon,
  │                abs_alt, rel_alt, battery_pct, local_north, local_east,
  │                local_down, heading_deg, mission{}, offboard{}, detections[]
  ▼
useTelemetryStream hook (React, Vite-built bundle)
  │  Auto-reconnects after 3 s close, 6 s stale watchdog
  ▼
TelemetryBox component
  → FC Link, WS status, State, Mode, Armed, Altitude, Heading, NED, Battery
```

**`/api/drone/status` snapshot (REST, one-shot):**
```json
{
  "state": "IDLE",
  "connected": true,
  "armed": false,
  "flight_mode": "STABILIZED",
  "heading_deg": 24.159671783447266
}
```

**`/api/health`:**
```json
{"status": "ok", "sim_mode": false}
```

### Files changed this sub-session
- `backend/main.py` — added `/assets` static mount
- `frontend/src/hooks/useTelemetryStream.js` — new hook (created earlier this session)
- `frontend/src/components/TelemetryBox.jsx` — replaced placeholder with live telemetry display
- `backend/app/static/` — populated with production build output

### Next
- Step 2: `backend/app/occupancy_grid.py` — build occupancy map from real LD06 data with heading rotation
- Integrate occupancy grid into `/ws/map` WebSocket
- Render occupancy map canvas on the dashboard

---

## Project Context Briefing — 2026-03-25

### What AeroDrop Is
GPS-denied indoor autonomous search-and-rescue drone system. FYP capstone, deadline mid-April 2026. Operator builds a mission on a web UI; drone arms, takes off, flies a lawnmower search pattern using offboard NED control; LD06 LiDAR builds an occupancy map; IMX500 AI camera records detections. Full simulation stack (ArduCopter SITL + MAVProxy in WSL2 on laptop) was developed and tested end-to-end.

### Hardware on This RPi (confirmed working)
| Component | Interface | Status |
|-----------|-----------|--------|
| LD06 LiDAR | `/dev/ttyAMA0` @ 230400 baud | Working — live point cloud confirmed |
| H7A3 FC MAVLink | `/dev/ttyAMA2` @ 115200 baud | Heartbeat confirmed |
| IMX500 AI camera | `rpicam-vid` subprocess | Stream + metadata working |
| Optical flow sensor | Not yet wired | Next hardware phase |
| ToF rangefinder | Not yet wired | Next hardware phase |

`dtoverlay=uart2` already in `/boot/firmware/config.txt`. H7A3 has `SERIAL2_PROTOCOL=2`, `SERIAL2_BAUD=115`. Do not touch these.

### What Was Validated in SITL (laptop)
- ARM → TAKEOFF → offboard lawnmower → obstacle stop (0.45 m) → auto-RTL → LAND
- Scout / Locate / Deliver task types all working
- Battery abort mid-mission, disarm watcher, occupancy map, telemetry stream (5 Hz), PDF/JSON export

### Critical Gap: This RPi Folder vs. Laptop Folder
The laptop folder has the full stack. This RPi folder currently only has the basic LiDAR + camera backend. **The entire `backend/drone/` module does not exist here yet:**
- `drone/controller.py` — MAVSDK + pymavlink wrapper, telemetry snapshot
- `drone/state_machine.py` — 7-state FSM (IDLE/ARMED/TAKEOFF/MISSION/RTL/LANDED/EMERGENCY)
- `drone/router.py` — all drone REST + WS endpoints, background watchers
- `drone/offboard_executor.py` — NED setpoint loop at 10 Hz, obstacle stop at 0.45 m
- `drone/task_executor.py` — Scout/Locate/Deliver → waypoint lists
- `drone/mission.py` — MAVSDK GPS mission (not used indoors)
- `drone/test_hitl.py` — smoke-test: connect → arm → takeoff → hover → land → disarm
- `app/occupancy_grid.py` — 12 m × 12 m grid, 0.2 m/cell, heading rotation, Bresenham ray-cast
- `app/detection_log.py` — thread-safe detection list with NED positions
- `app/lidar_sim.py`, `app/detection_sim.py` — SITL only, not needed here

Frontend on laptop also has the full mission planning + flight UI (Hero screen, MissionView, Zustand stores, all WS hooks with auto-reconnect, PDF/JSON export). This RPi currently has only the basic LiDAR/camera/telemetry placeholder frontend.

### Hardware Bringup Order (next goals)
1. Migrate full stack from laptop → this RPi folder
2. Backend starts cleanly — no import errors, LidarStreamer starts, DroneController connects to FC via MAVProxy UDP
3. LiDAR canvas and occupancy map working with real room data
4. ARM → LAND cycle through UI on real FC
5. Wire optical flow + ToF, set real driver params on H7A3 (`FLOW_TYPE`, `RNGFND1_TYPE`)
6. EKF3 bench test (props off) — confirm `local_north/east` stable, `is_local_position_ok=True`
7. GPS-denied hover — 1 m, 10 s, no drift
8. Full SAR mission — Scout a clear room, export PDF report

### Known Issues (from laptop development)
- Obstacle avoidance is stop-only — no path-around logic
- `camera_streamer.py` imports `cv2` at module level — `opencv-python-headless` must be installed or backend crashes on import
- `battery_pct` may read 0 or 100 if H7A3 battery monitor unconfigured (`BATT_MONITOR=0`)
- `MAVSDK_CONNECTION` must be UDP, not serial — MAVProxy must bridge first
- TelemetryBox offline message says "start SITL" — cosmetic, should say "check hardware"

### Python Environment
Venv: `~/pidrone/mavenv/` (has pymavlink + pyserial). Also needs: `mavsdk`, `opencv-python-headless`.

Hardware startup:
```bash
cd ~/pidrone
source mavenv/bin/activate
export SIM_MODE=false
export MAVSDK_CONNECTION="udpin://0.0.0.0:14552"
export GUIDED_PORT=14553
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Or: `bash start_hardware.sh --backend`

---
