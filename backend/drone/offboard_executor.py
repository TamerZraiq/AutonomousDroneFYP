"""
OffboardExecutor — flies a list of NED waypoints via pymavlink.

- Sends SET_POSITION_TARGET_LOCAL_NED at 10 Hz
- Stops advancing if nearest LiDAR obstacle < OBSTACLE_STOP_M
- Advances to next waypoint when within WAYPOINT_RADIUS_M
- Supports pause / resume / cancel
"""

import asyncio
import math
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.drone.controller import DroneController
    from backend.app.lidar_streamer import LidarStreamer

OBSTACLE_STOP_M  = 0.25   # metres — stop if obstacle in forward arc is closer than this
OBSTACLE_ARC_DEG = 60     # degrees — half-angle of forward arc to check (±60° = 120° cone)
WAYPOINT_RADIUS_M = 0.30  # metres — advance when this close to current waypoint
SETPOINT_HZ       = 10    # frequency of NED setpoint sends


@dataclass
class LocalWaypoint:
    north: float
    east:  float
    down:  float = -1.2   # negative = above takeoff (NED convention)
    yaw:   float = 0.0    # degrees, 0 = North


@dataclass
class OffboardStatus:
    active:     bool = False
    paused:     bool = False
    current_wp: int  = 0
    total_wp:   int  = 0
    finished:   bool = False
    blocked:    bool = False   # True when obstacle stop is active


class OffboardExecutor:
    def __init__(self, ctrl: "DroneController", lidar: "LidarStreamer"):
        self._ctrl   = ctrl
        self._lidar  = lidar
        self._status = OffboardStatus()
        self._pause_event  = asyncio.Event()
        self._cancel_event = asyncio.Event()
        self._pause_event.set()   # not paused initially

    @property
    def status(self) -> OffboardStatus:
        return OffboardStatus(**self._status.__dict__)

    async def run(self, waypoints: List[LocalWaypoint]):
        """Execute waypoint list. Blocks until finished or cancelled."""
        self._cancel_event.clear()
        self._pause_event.set()
        self._status = OffboardStatus(
            active=True,
            total_wp=len(waypoints),
        )

        interval = 1.0 / SETPOINT_HZ

        for i, wp in enumerate(waypoints):
            if self._cancel_event.is_set():
                break
            self._status.current_wp = i + 1

            # Drive toward this waypoint
            while not self._cancel_event.is_set():
                # Pause
                await self._pause_event.wait()

                # Obstacle check — only block for points in the forward arc.
                # LiDAR body frame: angle 0° = forward = y+, so
                # point_angle = atan2(x, y). Positive x = right, negative = left.
                xs, ys, _, _ = self._lidar.snapshot(max_out=200)
                blocked = False
                for x, y in zip(xs, ys):
                    dist = math.sqrt(x * x + y * y)
                    if dist > OBSTACLE_STOP_M:
                        continue
                    point_angle_deg = math.degrees(math.atan2(x, y))
                    if abs(point_angle_deg) < OBSTACLE_ARC_DEG:
                        blocked = True
                        break

                if blocked:
                    self._status.blocked = True
                    await asyncio.sleep(interval)
                    continue
                self._status.blocked = False

                # Send setpoint
                self._ctrl.send_ned_setpoint(wp.north, wp.east, wp.down, wp.yaw)

                # Check arrival
                snap = self._ctrl.snapshot()
                dist = math.sqrt(
                    (snap.local_north - wp.north) ** 2 +
                    (snap.local_east  - wp.east)  ** 2
                )
                if dist < WAYPOINT_RADIUS_M:
                    break

                await asyncio.sleep(interval)

        self._status.active   = False
        self._status.finished = not self._cancel_event.is_set()

    def pause(self):
        self._pause_event.clear()
        self._status.paused = True

    def resume(self):
        self._pause_event.set()
        self._status.paused = False

    def cancel(self):
        self._cancel_event.set()
        self._pause_event.set()   # unblock if paused so the loop can exit
        self._status.active = False
