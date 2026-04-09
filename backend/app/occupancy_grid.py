"""
OccupancyGrid — dynamic 2-D map built from real LiDAR data.

The drone does not know the room in advance. This grid is a 20 m × 20 m
canvas centred on the takeoff point (NED origin). As the drone moves and
the LD06 scans, cells get marked free (ray-cast) or occupied (hit).

Coordinate convention
---------------------
- World frame: North = +X, East = +Y (standard NED, ignoring Z here)
- Grid origin: top-left cell = (-10 m, -10 m) from takeoff
- cell (row, col):
    world_north = (HALF_SIZE - row) * RESOLUTION  — row 0 is northernmost
    world_east  =  (col - HALF_SIZE) * RESOLUTION

Usage
-----
grid = OccupancyGrid()
grid.update(drone_north, drone_east, heading_deg, body_frame_points)
payload = grid.serialise()   # → dict ready for JSON / /ws/map
"""

import math
import threading
from typing import List, Tuple

# Grid parameters
SIZE_M      = 20.0   # total side length in metres
RESOLUTION  = 0.10   # metres per cell — 10 cm resolution
CELLS       = int(SIZE_M / RESOLUTION)   # 200 × 200
HALF        = CELLS // 2                 # centre cell index

# Cell states
FREE     = 0
OCCUPIED = 1
UNKNOWN  = 2


class OccupancyGrid:
    def __init__(self):
        self._grid = [[UNKNOWN] * CELLS for _ in range(CELLS)]
        self._lock = threading.Lock()
        # Drone position in grid coords (updated each call)
        self._drone_row = HALF
        self._drone_col = HALF
        self._heading   = 0.0
        # Detection markers: list of (row, col)
        self._detections: List[Tuple[int, int]] = []

    # ── public ──────────────────────────────────────────────────────────────

    def update(self,
               drone_north: float,
               drone_east: float,
               heading_deg: float,
               body_frame_points: List[Tuple[float, float]]):
        """
        Integrate one LiDAR snapshot into the grid.

        Parameters
        ----------
        drone_north, drone_east : NED metres from takeoff origin
        heading_deg             : FC heading (yaw), degrees, 0 = North
        body_frame_points       : list of (x_m, y_m) in body frame
                                  (x forward, y left — LD06 convention)
        """
        dr, dc = self._ned_to_cell(drone_north, drone_east)
        heading_rad = math.radians(heading_deg)

        world_hits: List[Tuple[int, int]] = []
        for bx, by in body_frame_points:
            # Rotate body → world frame
            wn = bx * math.cos(heading_rad) - by * math.sin(heading_rad) + drone_north
            we = bx * math.sin(heading_rad) + by * math.cos(heading_rad) + drone_east
            hr, hc = self._ned_to_cell(wn, we)
            if self._in_bounds(hr, hc):
                world_hits.append((hr, hc))

        with self._lock:
            self._drone_row = dr
            self._drone_col = dc
            self._heading   = heading_deg
            for hr, hc in world_hits:
                self._bresenham_free(dr, dc, hr, hc)
                if self._in_bounds(hr, hc):
                    self._grid[hr][hc] = OCCUPIED

    def add_detection(self, north: float, east: float):
        """Mark a detection position on the map."""
        r, c = self._ned_to_cell(north, east)
        if self._in_bounds(r, c):
            with self._lock:
                self._detections.append((r, c))

    def serialise(self) -> dict:
        """Return a JSON-serialisable dict for /ws/map."""
        with self._lock:
            # Flatten to 1-D list: 0=free, 1=occupied, 2=unknown
            flat = [self._grid[r][c] for r in range(CELLS) for c in range(CELLS)]
            return {
                "cells":        CELLS,
                "size_m":       SIZE_M,
                "resolution":   RESOLUTION,
                "data":         flat,
                "drone_row":    self._drone_row,
                "drone_col":    self._drone_col,
                "heading_deg":  self._heading,
                "detections":   [{"row": r, "col": c} for r, c in self._detections],
            }

    def reset(self):
        with self._lock:
            self._grid = [[UNKNOWN] * CELLS for _ in range(CELLS)]
            self._detections.clear()
            self._drone_row = HALF
            self._drone_col = HALF

    # ── internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _ned_to_cell(north: float, east: float) -> Tuple[int, int]:
        row = HALF - int(round(north / RESOLUTION))
        col = HALF + int(round(east  / RESOLUTION))
        return row, col

    @staticmethod
    def _in_bounds(row: int, col: int) -> bool:
        return 0 <= row < CELLS and 0 <= col < CELLS

    def _bresenham_free(self, r0: int, c0: int, r1: int, c1: int):
        """Mark all cells along the ray from (r0,c0) to (r1,c1) as FREE,
        excluding the endpoint (which is the hit = OCCUPIED)."""
        dr = abs(r1 - r0)
        dc = abs(c1 - c0)
        sr = 1 if r1 > r0 else -1
        sc = 1 if c1 > c0 else -1
        err = dr - dc
        r, c = r0, c0
        while (r, c) != (r1, c1):
            if self._in_bounds(r, c) and self._grid[r][c] != OCCUPIED:
                self._grid[r][c] = FREE
            if r == r1 and c == c1:
                break
            e2 = 2 * err
            if e2 > -dc:
                err -= dc
                r   += sr
            if e2 <  dr:
                err += dr
                c   += sc
