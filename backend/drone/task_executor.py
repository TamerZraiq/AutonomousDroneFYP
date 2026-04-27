"""
TaskExecutor — converts a user scan task into a waypoint list and runs it.

User task (simple):
    {
        "target": "person",          # what the camera should look for
        "row_length": 3.0,           # metres per sweep row (how wide to cover)
        "rows": 5,                   # how many rows to sweep
        "altitude": 1.2,             # takeoff/cruise altitude in metres
    }

Pattern: boustrophedon (back-and-forth rows), 0.8 m row spacing.
The drone does NOT know the room in advance. It sweeps until:
  1. It reaches the end of a row (or LiDAR stops it — obstacle)
  2. All rows are done
  3. Mission is cancelled

Row orientation: first row goes North, shift East between rows.
Drone position at task start is treated as (0, 0) — the local origin.
"""

import asyncio
from typing import List, Optional, TYPE_CHECKING

from backend.drone.offboard_executor import LocalWaypoint, OffboardExecutor, OffboardStatus
from backend.app.detection_log import DetectionLog
from backend.app.occupancy_grid import OccupancyGrid

if TYPE_CHECKING:
    from backend.drone.controller import DroneController
    from backend.app.camera_streamer import latest_detection
    from backend.app.lidar_streamer import LidarStreamer

ROW_SPACING_M = 0.8   # metres between sweep rows


def build_sweep_waypoints(
    row_length: float,
    rows: int,
    altitude: float,
) -> List[LocalWaypoint]:
    """
    Generate boustrophedon sweep waypoints in local NED.
    Origin = drone position at mission start.
    Row 0: south end → north end (going North)
    Row 1: north end → south end (going South)
    ...
    """
    down = -altitude   # NED: negative down = positive altitude
    wps: List[LocalWaypoint] = []

    for row in range(rows):
        east = row * ROW_SPACING_M
        if row % 2 == 0:
            # going North
            wps.append(LocalWaypoint(north=row_length, east=east, down=down))
        else:
            # going South
            wps.append(LocalWaypoint(north=0.0, east=east, down=down))

    # Final: return to NED origin column (east=0) at same altitude
    wps.append(LocalWaypoint(north=0.0, east=0.0, down=down))
    return wps


class TaskExecutor:
    def __init__(
        self,
        ctrl: "DroneController",
        lidar: "LidarStreamer",
        detection_log: DetectionLog,
        grid: OccupancyGrid,
    ):
        self._ctrl      = ctrl
        self._lidar     = lidar
        self._log       = detection_log
        self._grid      = grid
        self._offboard  = OffboardExecutor(ctrl, lidar)
        self._task: Optional[asyncio.Task] = None
        self._target_class = ""

    @property
    def offboard_status(self) -> OffboardStatus:
        return self._offboard.status

    async def start(self, target: str, row_length: float, rows: int, altitude: float):
        """Start the scan mission. Returns immediately; mission runs in background."""
        self._target_class = target.lower()
        waypoints = build_sweep_waypoints(row_length, rows, altitude)

        # Offset waypoints by current NED position so (0,0) = where drone is now
        snap = self._ctrl.snapshot()
        for wp in waypoints:
            wp.north += snap.local_north
            wp.east  += snap.local_east

        self._task = asyncio.create_task(
            self._run(waypoints, altitude)
        )

    async def _run(self, waypoints: List[LocalWaypoint], altitude: float):
        # Run offboard + detection monitoring in parallel
        await asyncio.gather(
            self._offboard.run(waypoints),
            self._monitor_detections(),
            self._update_map(),
        )

    async def _monitor_detections(self):
        """Poll camera_streamer for detections matching target class."""
        from backend.app import camera_streamer
        last_ts = 0.0
        while self._offboard.status.active or not self._offboard.status.finished:
            await asyncio.sleep(0.2)
            det = camera_streamer.latest_detection
            if not det or not det.get("objects"):
                continue
            if det.get("timestamp", 0) == last_ts:
                continue
            last_ts = det["timestamp"]

            snap = self._ctrl.snapshot()
            for obj in det["objects"]:
                label = obj.get("label", "").lower()
                conf  = obj.get("confidence", 0.0)
                if self._target_class in label and conf > 0.5:
                    # Capture current frame
                    frame = camera_streamer.latest_frame
                    self._log.add(
                        object_class=label,
                        confidence=conf,
                        north=snap.local_north,
                        east=snap.local_east,
                        frame_jpg=frame,
                    )
                    self._grid.add_detection(snap.local_north, snap.local_east)
                    print(f"[TaskExecutor] Detection: {label} {conf:.2f} at N{snap.local_north:.2f} E{snap.local_east:.2f}")

    async def _update_map(self):
        """Feed LiDAR snapshots into occupancy grid at ~5 Hz."""
        while self._offboard.status.active or not self._offboard.status.finished:
            await asyncio.sleep(0.2)
            snap = self._ctrl.snapshot()
            xs, ys, _, _ = self._lidar.snapshot(max_out=500)
            body_pts = list(zip(xs, ys))
            if body_pts:
                self._grid.update(
                    snap.local_north,
                    snap.local_east,
                    snap.heading_deg,
                    body_pts,
                )

    def cancel(self):
        self._offboard.cancel()
        if self._task:
            self._task.cancel()

    def pause(self):
        self._offboard.pause()

    def resume(self):
        self._offboard.resume()
