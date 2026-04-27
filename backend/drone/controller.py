"""
DroneController — hardware path only (SIM_MODE=false).

Opens two simultaneous connections to ArduCopter via MAVProxy UDP bridge:
  - MAVSDK  udpin://0.0.0.0:14552  → telemetry, arm, takeoff, land, RTL
  - pymavlink udpin:0.0.0.0:14553  → SET_POSITION_TARGET_LOCAL_NED at 10 Hz

Six background asyncio tasks keep TelemetrySnapshot current.
Call connect() once at startup; it returns when MAVSDK is healthy or raises.
"""

import asyncio
import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import pymavlink.mavutil as mavutil
from mavsdk import System
from mavsdk.action import ActionError
from mavsdk.telemetry import FlightMode


# ── env-configurable connection strings ──────────────────────────────────────
MAVSDK_CONNECTION = os.getenv("MAVSDK_CONNECTION", "udpin://0.0.0.0:14552")
GUIDED_PORT       = int(os.getenv("GUIDED_PORT", "14553"))


@dataclass
class TelemetrySnapshot:
    connected:    bool  = False
    armed:        bool  = False
    flight_mode:  str   = "UNKNOWN"
    lat:          float = 0.0
    lon:          float = 0.0
    abs_alt:      float = 0.0
    rel_alt:      float = 0.0
    battery_pct:  float = 0.0
    local_north:  float = 0.0
    local_east:   float = 0.0
    local_down:   float = 0.0
    heading_deg:  float = 0.0


class DroneController:
    def __init__(self):
        self._drone   = System()
        self._mav     = None          # pymavlink connection
        self._snap    = TelemetrySnapshot()
        self._snap_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._override_throttle: Optional[int] = None
        self._override_task: Optional[asyncio.Task] = None

    # ── public API ────────────────────────────────────────────────────────────

    async def connect(self, timeout: float = 30.0):
        """Connect MAVSDK and pymavlink. Raises RuntimeError on timeout."""
        print(f"[DroneController] Connecting MAVSDK → {MAVSDK_CONNECTION}")
        await self._drone.connect(system_address=MAVSDK_CONNECTION)

        deadline = asyncio.get_event_loop().time() + timeout
        async for state in self._drone.core.connection_state():
            if state.is_connected:
                print("[DroneController] MAVSDK connected ✓")
                break
            if asyncio.get_event_loop().time() > deadline:
                raise RuntimeError("MAVSDK connection timed out")

        # pymavlink — runs in a thread executor so it doesn't block the loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._open_pymavlink)

        # Start background telemetry tasks
        self._tasks = [
            asyncio.create_task(self._poll_connection()),
            asyncio.create_task(self._poll_armed()),
            asyncio.create_task(self._poll_flight_mode()),
            asyncio.create_task(self._poll_position()),
            asyncio.create_task(self._poll_battery()),
            asyncio.create_task(self._poll_local_position()),
            asyncio.create_task(self._poll_heading()),
        ]
        print("[DroneController] Background telemetry tasks started ✓")

    def _open_pymavlink(self):
        print(f"[DroneController] Opening pymavlink → udpin:0.0.0.0:{GUIDED_PORT}")
        self._mav = mavutil.mavlink_connection(
            f"udpin:0.0.0.0:{GUIDED_PORT}",
            source_system=255,
        )
        self._mav.wait_heartbeat(timeout=15)
        print("[DroneController] pymavlink heartbeat received ✓")

    async def disconnect(self):
        self._stop_override()
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    def snapshot(self) -> TelemetrySnapshot:
        """Return a copy of the latest telemetry (thread-safe read)."""
        return TelemetrySnapshot(**self._snap.__dict__)

    async def stream_telemetry(self, hz: float = 5.0):
        """Async generator yielding a snapshot at the given rate."""
        interval = 1.0 / hz
        while True:
            yield self.snapshot()
            await asyncio.sleep(interval)

    # ── flight commands ───────────────────────────────────────────────────────

    async def arm(self):
        await self._drone.action.arm()

    def _try_mode(self, mode_num: int, name: str) -> bool:
        """Try to switch to mode_num via pymavlink. Returns True if FC accepts within 3 s."""
        if self._mav is None:
            return False
        self._mav.set_mode(mode_num)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            msg = self._mav.recv_match(type="HEARTBEAT", blocking=True, timeout=1.0)
            if msg and msg.custom_mode == mode_num:
                print(f"[DroneController] {name} (mode {mode_num}) ✓")
                return True
        print(f"[DroneController] {name} (mode {mode_num}) rejected")
        return False

    def _send_throttle_override(self, throttle: int):
        """Override RC channel 3 (throttle). 65535 = leave other channels alone."""
        if self._mav is None:
            return
        self._mav.mav.rc_channels_override_send(
            1, 1,
            65535, 65535, throttle, 65535,
            65535, 65535, 65535, 65535,
        )

    async def _rc_override_loop(self):
        """Send throttle override every 0.4 s so it doesn't time out (RC_OVERRIDE_TIME=3 s)."""
        loop = asyncio.get_running_loop()
        try:
            while True:
                if self._override_throttle is not None:
                    await loop.run_in_executor(
                        None, self._send_throttle_override, self._override_throttle
                    )
                await asyncio.sleep(0.4)
        except asyncio.CancelledError:
            await loop.run_in_executor(None, self._send_throttle_override, 0)

    def _stop_override(self):
        self._override_throttle = None
        if self._override_task and not self._override_task.done():
            self._override_task.cancel()
        self._override_task = None

    async def takeoff(self, alt: float = 1.5):
        """
        Take off using FLOWHOLD (optical flow velocity hold) with ALT_HOLD as fallback.
        Both modes bypass the EKF position requirement that blocks GUIDED mode.
        Altitude is controlled via RC channel 3 override.
        """
        loop = asyncio.get_running_loop()

        # FLOWHOLD (22) = optical flow + baro, no position required
        # ALT_HOLD (2)  = baro only, always accepted
        ok = await loop.run_in_executor(None, self._try_mode, 22, "FLOWHOLD")
        if not ok:
            ok = await loop.run_in_executor(None, self._try_mode, 2, "ALT_HOLD")
        if not ok:
            raise RuntimeError("FC rejected both FLOWHOLD and ALT_HOLD — check arming state")

        # THR_DZ=100 means deadband ±100 around 1500. Use 1700 to climb clearly above it.
        self._override_throttle = 1700
        if self._override_task is None or self._override_task.done():
            self._override_task = asyncio.create_task(self._rc_override_loop())

        print(f"[DroneController] Climbing to {alt} m")
        deadline = loop.time() + 30.0
        while loop.time() < deadline:
            await asyncio.sleep(0.3)
            if self.snapshot().rel_alt >= alt * 0.85:
                self._override_throttle = 1500  # midpoint = hold altitude
                print(f"[DroneController] Hovering at {self.snapshot().rel_alt:.2f} m ✓")
                return

        self._override_throttle = 1500
        raise RuntimeError(f"Takeoff timed out — only reached {self.snapshot().rel_alt:.2f} m")

    async def land(self):
        if self._override_task and not self._override_task.done():
            self._override_throttle = 1350  # below deadband → gentle descent
            deadline = asyncio.get_running_loop().time() + 20.0
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.3)
                if self.snapshot().rel_alt < 0.15:
                    break
            self._stop_override()
            await asyncio.sleep(0.5)
            try:
                await self._drone.action.disarm()
            except Exception:
                pass
        else:
            await self._drone.action.land()

    async def rtl(self):
        await self.land()

    async def disarm(self):
        self._stop_override()
        await self._drone.action.disarm()

    # ── motor test (pymavlink) ───────────────────────────────────────────────

    def motor_test(self, motor: int, throttle_pct: float, duration: float = 2.0):
        """
        Spin one motor via MAV_CMD_DO_MOTOR_TEST (no arming required).
        motor: 1-4 (ArduCopter motor numbering)
        throttle_pct: 0-100
        duration: seconds to spin
        """
        if self._mav is None:
            raise RuntimeError("pymavlink not connected")
        self._mav.mav.command_long_send(
            1, 1,  # target system, target component
            mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
            0,             # confirmation
            motor,         # param1: motor number (1-based)
            0,             # param2: throttle type 0 = percent
            throttle_pct,  # param3: throttle %
            duration,      # param4: timeout seconds
            0, 0, 0,
        )

    # ── NED setpoint (pymavlink) ──────────────────────────────────────────────

    def send_ned_setpoint(self, north: float, east: float, down: float, yaw: float = 0.0):
        """Send a position setpoint in body NED frame (metres). Non-blocking."""
        if self._mav is None:
            return
        self._mav.mav.set_position_target_local_ned_send(
            0,          # time_boot_ms (not used)
            1, 1,       # target system, target component
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000_1111_1111_1000,  # position only (ignore vel/accel/yaw-rate)
            north, east, down,
            0, 0, 0,    # velocity
            0, 0, 0,    # acceleration
            yaw, 0,     # yaw, yaw_rate
        )

    # ── background telemetry tasks ────────────────────────────────────────────

    async def _poll_connection(self):
        try:
            async for state in self._drone.core.connection_state():
                async with self._snap_lock:
                    self._snap.connected = state.is_connected
        except asyncio.CancelledError:
            pass

    async def _poll_armed(self):
        try:
            async for arm in self._drone.telemetry.armed():
                async with self._snap_lock:
                    self._snap.armed = arm
        except asyncio.CancelledError:
            pass

    async def _poll_flight_mode(self):
        try:
            async for mode in self._drone.telemetry.flight_mode():
                async with self._snap_lock:
                    self._snap.flight_mode = mode.name
        except asyncio.CancelledError:
            pass

    async def _poll_position(self):
        try:
            async for pos in self._drone.telemetry.position():
                async with self._snap_lock:
                    self._snap.lat     = pos.latitude_deg
                    self._snap.lon     = pos.longitude_deg
                    self._snap.abs_alt = pos.absolute_altitude_m
                    self._snap.rel_alt = pos.relative_altitude_m
        except asyncio.CancelledError:
            pass

    async def _poll_battery(self):
        try:
            async for bat in self._drone.telemetry.battery():
                pct = bat.remaining_percent
                # skip sentinel values that indicate unconfigured monitor
                if pct is not None and 0 < pct <= 100:
                    async with self._snap_lock:
                        self._snap.battery_pct = pct
        except asyncio.CancelledError:
            pass

    async def _poll_local_position(self):
        try:
            async for pos in self._drone.telemetry.position_velocity_ned():
                async with self._snap_lock:
                    self._snap.local_north = pos.position.north_m
                    self._snap.local_east  = pos.position.east_m
                    self._snap.local_down  = pos.position.down_m
        except asyncio.CancelledError:
            pass

    async def _poll_heading(self):
        try:
            async for att in self._drone.telemetry.attitude_euler():
                async with self._snap_lock:
                    self._snap.heading_deg = att.yaw_deg % 360
        except asyncio.CancelledError:
            pass
