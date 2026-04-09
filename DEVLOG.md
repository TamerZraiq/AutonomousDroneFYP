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

## Project State — as of 2026-03-25 end of session

### Hardware confirmed working
| Component | Interface | Status |
|-----------|-----------|--------|
| LD06 LiDAR | `/dev/ttyAMA0` @ 230400 baud | ✅ Live point cloud on dashboard |
| H7A3 FC MAVLink | `/dev/ttyAMA2` @ 115200 baud | ✅ Full telemetry pipeline confirmed |
| IMX500 AI camera | `rpicam-vid` subprocess | ✅ Stream + metadata working |
| Matek 3901-L0X (optical flow + ToF) | Not yet wired | ⬜ Next hardware phase |

`dtoverlay=uart2` in `/boot/firmware/config.txt`. H7A3 `SERIAL2_PROTOCOL=2`, `SERIAL2_BAUD=115`. Do not touch.

### What exists in this repo right now
**Backend:**
- `backend/main.py` — SIM_MODE flag, lidar always on, drone module loaded when `SIM_MODE=false`
- `backend/app/lidar_streamer.py` — LD06 serial reader, ring buffer, snapshot()
- `backend/app/camera_streamer.py` — rpicam-vid subprocess, MJPEG + AI metadata
- `backend/drone/controller.py` — MAVSDK + pymavlink, 7 telemetry tasks, TelemetrySnapshot
- `backend/drone/state_machine.py` — 7-state FSM
- `backend/drone/router.py` — `/api/drone/status` + `/ws/telemetry`
- `backend/drone/test_hitl.py` — smoke-test script

**Still to build (not yet in this repo):**
- `backend/drone/offboard_executor.py` — NED setpoint loop, obstacle stop
- `backend/drone/task_executor.py` — Scout/Locate/Deliver task types
- `backend/app/occupancy_grid.py` — 12 m × 12 m map, heading rotation, Bresenham
- `backend/app/detection_log.py` — thread-safe detection list
- Full frontend mission planning UI (Hero screen, MissionView, FlightControl, LaunchPanel, OccupancyMap, full TelemetryBox, Zustand stores, PDF/JSON export)

### Python environment
Venv: `~/pidrone/venv/`
Installed: fastapi, uvicorn, pymavlink, mavsdk, MAVProxy, future, opencv-python-headless, pyserial, numpy

### How to start the system
Terminal 1 — MAVProxy bridge:
```bash
source ~/pidrone/venv/bin/activate
mavproxy.py --master=/dev/ttyAMA2 --baudrate=115200 \
    --out=udpout:0.0.0.0:14552 --out=udpout:0.0.0.0:14553 --daemon
```
Terminal 2 — backend:
```bash
cd ~/pidrone && source venv/bin/activate
export SIM_MODE=false
export MAVSDK_CONNECTION="udpin://0.0.0.0:14552"
export GUIDED_PORT=14553
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Access dashboard: `http://172.20.10.2:8000`

Frontend build (after any frontend changes):
```bash
cd ~/pidrone/frontend && npm run build && cp -r dist/* ../backend/app/static/
```

### Known issues / gotchas
- `is_armable=False`, `local_pos_ok=False` — expected until Matek 3901-L0X wired and FC params set
- `battery_pct` shows N/A — `BATT_MONITOR=0` on H7A3, not configured
- Obstacle avoidance (when built) will be stop-only — no path-around logic
- `MAVSDK_CONNECTION` must be UDP — MAVProxy must be running first
- Vite dev server hangs on Pi under load — always use production build for runtime

### Hardware bringup checklist
- [x] LiDAR canvas live in browser
- [x] FC ↔ RPi MAVLink pipeline (MAVProxy + MAVSDK + pymavlink)
- [x] Live telemetry on dashboard (flight mode, heading, armed, altitude)
- [x] Matek 3901-L0X optical flow + ToF — confirmed working (opt_qua ~43, opt_m_x/y responsive, EK3_SRC1_POSZ=2)
- [x] Motors 2/3/4 confirmed spinning via motor test (PWM 1400, MOT_PWM_TYPE=0)
- [~] Motor 1 (S1 pad) FAULTY — pad/trace dead on FC, confirmed by ESC swap. Drone cannot fly yet.
- [ ] EKF3 bench test — `local_pos_ok=True`, stable NED readings
- [x] ARM / TAKEOFF / LAND / RTL / EMERGENCY / RESET endpoints built
- [x] Occupancy grid built (20×20m dynamic, Bresenham ray-cast, heading rotation)
- [x] `/ws/map` WebSocket at 2 Hz
- [x] Detection log with NED position + JPEG frame capture
- [x] Offboard executor (10 Hz NED setpoints, obstacle stop at 0.45m)
- [x] Task executor (boustrophedon sweep, detection monitoring, map update)
- [x] Full mission UI frontend (flight controls, mission config, occupancy map, LiDAR, camera tabs, detection list, PDF export)
- [ ] Full SAR pipeline validated hand-held (EKF3 health, arm → mission → RTL)
- [ ] Motor 1 fix → GPS-denied hover test
- [ ] Full autonomous SAR mission with real flight + PDF export

### Motor 1 fault — testing strategy
S1 pad is dead (FC hardware fault). Motors 2/3/4 work. Drone cannot generate lift.
Plan: validate entire SAR software pipeline hand-held. Person physically carries drone around room — optical flow sees real motion, LiDAR scans real environment, occupancy map builds with real heading rotation, camera runs AI detection. All software layers fully exercised without flight risk. Motor 1 fix required before actual autonomous hover/mission.

---

## Session 1 continued — Git / .gitignore cleanup

### Problem
VS Code Source Control showed "branch has no upstream" when trying to push. Root cause: `SCRUM-145-feature/RPiFCpipeline` was a new local branch never pushed to `origin`.

MAVProxy runtime files were also staged for commit and should never be in the repo:
- `mav.parm` — FC parameter dump downloaded by MAVProxy on connect
- `mav.tlog` — binary telemetry log written continuously by MAVProxy
- `mav.tlog.raw` — raw binary log
- `--metadata-format` — stray file from rpicam-vid metadata output

### Fix
Added to root `.gitignore`:
```
mav.parm
mav.tlog
mav.tlog.raw
mav*.tlog
mav*.parm
--metadata-format
```
Removed already-staged files with `git rm --cached`. Set upstream with `git push -u origin SCRUM-145-feature/RPiFCpipeline`.

---

## Session 2 — 2026-04-04

### Hardware update received at session start
- **Optical flow (Matek 3901-L0X):** Confirmed working — `opt_qua ~43`, `opt_m_x/y` responsive, `EK3_SRC1_POSZ=2` set on FC
- **Motors 2/3/4:** Confirmed spinning via pymavlink `MAV_CMD_DO_MOTOR_TEST`, PWM 1400, `throttle_type=1`, `MOT_PWM_TYPE=0`
- **Motor 1 (S1 pad):** Confirmed faulty — S1 pad or FC copper trace is dead. Isolated by swapping ESC signal wires. Drone cannot fly. Not fixed.
- **Testing strategy:** Full SAR pipeline validated hand-held. Person carries drone around room. Software fully exercised without props.
- **PDB issue (end of session):** PDB 5V rail not powering FC. FC powered via USB for continued testing. Optical flow may not be powered via USB depending on wiring. `local_pos_ok` may be False — drone marker won't track on map but all other pipeline components still testable.

---

### Full SAR Pipeline Implementation

**Goal:** User types a target (e.g. "person"), hits START MISSION, drone autonomously sweeps the room, logs detections with NED positions and camera frames, auto-RTLs, user exports PDF.

#### Philosophy change — occupancy grid
Previous plan had a fixed 12×12m pre-defined room. Changed to a **dynamic discovery approach**: 20×20m canvas centred on takeoff origin (NED 0,0). No room size specified. Grid fills organically as LiDAR data arrives. The room maps itself.

---

#### Files created

**`backend/app/occupancy_grid.py`**
- 20×20m grid, 0.10m/cell resolution → 200×200 = 40,000 cells
- Cell states: `FREE=0`, `OCCUPIED=1`, `UNKNOWN=2`
- `update(drone_north, drone_east, heading_deg, body_frame_points)`: rotates body-frame LiDAR points to world frame using real IMU heading, then Bresenham ray-casts from drone position — marks ray path as FREE, endpoint as OCCUPIED
- `add_detection(north, east)`: marks a detection position on the grid for rendering
- `serialise()`: returns flat 1-D list + drone position + heading + detection markers for `/ws/map`
- `reset()`: clears grid between missions
- Thread-safe via `threading.Lock`

**`backend/app/detection_log.py`**
- `Detection` dataclass: `object_class`, `confidence`, `north`, `east`, `timestamp`, `frame_jpg` (raw JPEG bytes, optional)
- `DetectionLog`: thread-safe list via `threading.Lock`
- `add()`, `all()`, `as_dicts()` (no frame bytes — safe for JSON/WS), `clear()`

**`backend/drone/offboard_executor.py`**
- Sends `SET_POSITION_TARGET_LOCAL_NED` via pymavlink at 10 Hz
- `LocalWaypoint` dataclass: `north`, `east`, `down=-1.2`, `yaw=0.0`
- `OffboardStatus` dataclass: `active`, `paused`, `current_wp`, `total_wp`, `finished`, `blocked`
- Obstacle stop: if LiDAR nearest < `OBSTACLE_STOP_M=0.45m`, holds current setpoint, sets `blocked=True`
- Waypoint advance when within `WAYPOINT_RADIUS_M=0.30m`
- `pause()` / `resume()` via `asyncio.Event`; `cancel()` sets cancel event and unblocks pause

**`backend/drone/task_executor.py`**
- `build_sweep_waypoints(row_length, rows, altitude)` → boustrophedon pattern:
  - Even rows go North, odd rows go South, each shifted East by `ROW_SPACING_M=0.8m`
  - Final waypoint returns to NED origin
- `TaskExecutor.start()`: offsets waypoints by current NED position (so drone's current location is local origin), spawns `_run()` as asyncio task
- Three parallel coroutines inside `_run()`:
  1. `offboard_executor.run(waypoints)` — flies the sweep
  2. `_monitor_detections()` — polls `camera_streamer.latest_detection` at 5 Hz, matches target class, logs NED + captures JPEG frame, marks grid
  3. `_update_map()` — feeds LiDAR snapshot into occupancy grid at 5 Hz with current heading

**`backend/drone/router.py`** — full rewrite, added:
- REST: `POST /api/drone/arm`, `takeoff`, `land`, `rtl`, `emergency`, `reset`
- REST: `POST /api/drone/task/start` (body: `{target, row_length, rows, altitude}`), `task/cancel`, `task/pause`, `task/resume`
- REST: `POST /api/drone/detections/clear`
- REST: `GET /api/drone/report/json` — returns all detections with `frame_b64` (base64 JPEG) for each detection that has a frame
- WS: `/ws/telemetry` (5 Hz) — now includes `offboard{}` status + `detections[]`
- WS: `/ws/map` (2 Hz) — full grid serialisation
- `set_dependencies(ctrl, sm, lidar)` — injects all singletons, constructs `DetectionLog`, `OccupancyGrid`, `TaskExecutor`
- `_watch_mission_end()` background task: polls offboard status, auto-triggers RTL when sweep finishes

**`backend/app/camera_streamer.py`** — added:
- `latest_frame: bytes | None` global — stores raw JPEG bytes of the most recent encoded frame
- Updated in `frame_generator()` after each `cv2.imencode()` call
- Used by `task_executor._monitor_detections()` for frame capture at detection moment

**`backend/main.py`** — updated `set_controller` → `set_dependencies(ctrl, sm, lidar)` to pass lidar reference

---

#### Files created — frontend

**`frontend/src/hooks/useMapStream.js`**
- Connects to `/ws/map`, parses grid payload, 3s auto-reconnect, 8s stale watchdog
- Returns `{ map, status }`

**`frontend/src/components/OccupancyMap.jsx`**
- Canvas 500×500px, `id="occupancy-canvas"` (read by PDF export)
- Green = FREE, Red = OCCUPIED, dark = UNKNOWN
- Yellow circles = detection markers
- Cyan dot + white heading arrow = drone position + orientation
- 1m scale bar bottom-left
- "Save PNG" button → `canvas.toDataURL()` download

**`frontend/src/App.jsx`** — full rewrite:
- **Top bar:** FC link status, SM state, armed indicator
- **Left sidebar:** flight controls (ARM/TAKEOFF/RTL/LAND/RESET/EMERGENCY), mission config form (target string, row length, rows, altitude, estimated coverage m²), START MISSION / PAUSE / RESUME / CANCEL, waypoint progress bar, Export PDF button + detection count
- **Centre:** tab switcher — Occupancy Map / LiDAR / Camera
- **Right sidebar:** TelemetryBox + detection list (class, confidence, NED position)
- All flight buttons gated by SM state (disabled when invalid)
- EMERGENCY always enabled
- `exportPDF()`: lazy-imports jsPDF + autotable, renders map canvas as PNG, detection table, one page per detection frame

**`frontend/src/index.css`** — added Tailwind component classes: `.btn-primary`, `.btn-secondary`, `.input`

**`frontend/package.json`** — added `jspdf`, `jspdf-autotable`

---

#### `start.sh` created
```bash
./start.sh             # MAVProxy daemon (&) + backend (foreground)
./start.sh --mavproxy  # MAVProxy foreground only
./start.sh --backend   # backend only
./start.sh --build     # npm run build + cp to static
```
- `--daemon` flag removed from combined mode (was blocking script before uvicorn started)

---

#### Sweep pattern example output (3m rows, 4 rows, 1.2m alt)
```
WP1: N3.0  E0.0  D-1.2   (row 0, going North)
WP2: N0.0  E0.8  D-1.2   (row 1, going South)
WP3: N3.0  E1.6  D-1.2   (row 2, going North)
WP4: N0.0  E2.4  D-1.2   (row 3, going South)
WP5: N0.0  E0.0  D-1.2   (return to origin)
```

---

### Known limitations at end of session
- Motor 1 / S1 pad fault — drone cannot fly, pipeline tested hand-held only
- PDB 5V rail fault — FC running on USB, optical flow may be unpowered → `local_pos_ok=False` possible → drone marker won't track on occupancy map
- Obstacle avoidance is stop-only (no path-around)
- PDF camera frame pages are scaffolded but frames require `/api/drone/report/json` `frame_b64` field to render (not yet wired into PDF page image insertion)

### Next
- Validate pipeline hand-held: ARM → TAKEOFF → START MISSION → carry drone → RTL → Export PDF
- Fix PDB 5V rail (Motor 1 fix + PDB) → real hover test
- Wire PDF frame images into jsPDF pages

---

## Session 4 — 2026-04-09

### Summary
Drone armed and took off successfully (1.02A draw confirmed). Frontend data layout redesigned. Multiple bugs diagnosed and fixed: stale MAVProxy daemon processes, wrong UDP address in start.sh, takeoff command rejected by FC (result=4), SAR mission always blocked by false LiDAR obstacle readings from loose wiring/components. Decision made to properly mount all hardware on chassis before next flight test.

---

### Part 1 — Frontend Data Layout Redesign

**New grid layout (6 cols × 3 rows):**
- Col 1–2, Row 1: Telemetry
- Col 1–2, Row 2: Camera Feed
- Col 3–4, Rows 1–2: LiDAR (full height)
- Col 5–6, Rows 1–2: Occupancy Map (full height)
- Col 1–6, Row 3: Detections (full width, 100px)

Used explicit CSS grid line syntax (`gridColumn: "3 / 5"` etc.) instead of `span`. Canvas `size` prop set to 460 for internal resolution. Canvas display scaled via `width: "100%"; height: "auto"; maxHeight: "100%"; aspectRatio: "1 / 1"` to fill box without stretching.

**Files:** `frontend/src/App.jsx`, `frontend/src/components/LidarCanvas.jsx`, `frontend/src/components/OccupancyMap.jsx`

---

### Part 2 — start.sh: Stale MAVProxy Daemons + Wrong UDP Address

**Symptom:** Intermittent — FC works but LiDAR/camera don't, or vice versa. FC arms briefly then disconnects.

**Root causes:**
1. Every `./start.sh` added a new `mavproxy.py --daemon` without killing the previous one. Multiple daemons compete for `/dev/ttyAMA2`; only one wins the serial port. Backend randomly connects to a dead instance.
2. `--out=udpout:0.0.0.0:14552` sends to broadcast address — unreliable on Linux loopback. Should be `127.0.0.1`.
3. `sleep 3` race condition — backend could start before MAVProxy had received its first heartbeat.

**Fix:**
- Added `pkill -f "mavproxy.py"` + `pkill -f "uvicorn backend.main"` at startup
- Changed all `udpout:0.0.0.0` → `udpout:127.0.0.1`
- Replaced `sleep 3` with a 15-second port-readiness poll on `:14552`

**Note:** The port-check polls for a listening socket on 14552, which is actually MAVSDK's socket (not MAVProxy's outbound). Workaround: user starts MAVProxy via `./start.sh --mavproxy` then backend via `./start.sh --backend` separately. Both confirmed working.

**Files:** `start.sh`

---

### Part 3 — Takeoff Rejected (result=4, MAV_RESULT_UNSUPPORTED)

**Root cause:** Previous impl sent `MAV_CMD_NAV_TAKEOFF` via `command_long`. ArduCopter returns UNSUPPORTED (4) for this path. MAVSDK `action.takeoff()` also fails — it doesn't auto-switch ArduCopter to GUIDED mode.

**Fix:** Replaced with NED setpoint climb:
1. `pymavlink.set_mode(4)` → GUIDED mode
2. Capture current NED position from snapshot
3. Send `SET_POSITION_TARGET_LOCAL_NED` at `[north, east, -alt]` every 200ms
4. Poll `rel_alt` until ≥ 85% of target or 20s timeout

Same mechanism as offboard executor waypoints. **Confirmed working — drone reached ~1.0m.**

**Files:** `backend/drone/controller.py`

---

### Part 4 — SAR Mission Permanently Blocked

**Root cause 1:** `OBSTACLE_STOP_M = 0.45m` checked all 360°. Indoor walls always within 45cm somewhere.

**Root cause 2:** Initial forward-arc fix had a coordinate frame bug — incorrectly transforming LiDAR body-frame points to world frame.

**Fix:** Reduced threshold to 0.25m. Forward-arc check now in pure body frame: `point_angle = atan2(x, y)` (LiDAR frame: 0° = forward = y+). Block only if `|point_angle| < 60°`. Side/rear obstacles ignored.

**Root cause 3 (physical):** Still blocked after code fix. Loose wires, ESC cables, connectors, and components within 25cm of LiDAR in the forward sector registered as solid obstacles.

**Decision:** Mount all electronics on drone chassis (no props) before next test. Clears LiDAR scan plane and gives realistic sensor geometry.

**Files:** `backend/drone/offboard_executor.py`

---

### Part 5 — Camera Feed Silent Failure

`AICamFeed.jsx` had no error handling. If `rpicam-vid` fails, `<img>` shows nothing with no feedback.

**Fix:** Added `status` state (`loading/ok/error`), `onError` handler, "Camera stream unavailable" message, and Retry button.

**Files:** `frontend/src/components/AICamFeed.jsx`

---

### Hardware status end of session

| Component | Status |
|---|---|
| H7A3 FC — Arm | ✅ Working |
| Takeoff (NED setpoints) | ✅ Confirmed (~1.0m, 1.02A) |
| LD06 LiDAR | ✅ Live |
| Optical flow (Matek 3901-L0X) | ✅ EKF healthy |
| IMX500 AI camera | ⚠️ Not confirmed this session |
| Motor 1 replacement ESC | ⏳ Awaiting part |
| SAR mission end-to-end | ⏳ Pending chassis mount |

### Next
1. Mount all electronics on chassis (no props)
2. Confirm LiDAR scan plane clear with real mounting geometry
3. Validate SAR mission hand-held: arm → takeoff → sweep → RTL
4. Confirm camera stream working
5. Motor 1 ESC replacement → first free-flight hover test

---
