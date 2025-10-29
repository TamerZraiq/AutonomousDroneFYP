# ~/pidrone/backend/lidar_streamer.py
import serial, struct, threading, time
from collections import deque
from typing import Tuple, List

SERIAL_PORT = "/dev/ttyAMA0"
BAUD = 230400
PACKET_LENGTH = 47
MEASUREMENT_LENGTH = 12
MESSAGE_FORMAT = "<xBHH" + "HB" * MEASUREMENT_LENGTH + "HHB"

class LidarStreamer:
    """
    Single-owner LD06 reader. Runs a background thread that:
      - reads frames from /dev/ttyAMA0
      - decodes into (x,y,c) points
      - keeps a ring buffer of latest points (bounded)
    Other code can call snapshot() to get a downsampled set to send to clients.
    """
    def __init__(self, max_points:int=2000):
        self.max_points = max_points
        self._points = deque(maxlen=max_points)  # (x,y,c)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thr = None
        self._ser = None

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=2.0)
        if self._ser:
            try: self._ser.close()
            except: pass

    def _open_serial(self):
        self._ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0.5)

    def _parse_packet(self, data:bytes):
        # returns list of (angle_deg, dist_mm, conf)
        length, speed, start_angle, *pos_data, stop_angle, timestamp, crc = struct.unpack(MESSAGE_FORMAT, data)
        start_angle /= 100.0
        stop_angle  /= 100.0
        if stop_angle < start_angle:
            stop_angle += 360.0
        step = (stop_angle - start_angle) / (MEASUREMENT_LENGTH - 1)
        angles = [start_angle + step * i for i in range(MEASUREMENT_LENGTH)]
        dists  = pos_data[0::2]
        confs  = pos_data[1::2]
        return list(zip(angles, dists, confs))

    @staticmethod
    def _polar_to_xy(angle_deg:float, dist_mm:int) -> Tuple[float,float]:
        # meters, sensor at origin. angle 0° forward (Y+), like earlier.
        import math
        a = math.radians(angle_deg)
        r = dist_mm / 1000.0
        x = math.sin(a) * r
        y = math.cos(a) * r
        return x, y

    def _run(self):
        while not self._stop.is_set():
            try:
                if not self._ser or not self._ser.is_open:
                    self._open_serial()

                # sync on 0x54, 0x2C, then read the rest
                b = self._ser.read()
                if b != b'\x54':
                    continue
                b2 = self._ser.read()
                if b2 != b'\x2C':
                    continue
                packet = b'\x54\x2C' + self._ser.read(PACKET_LENGTH - 2)
                if len(packet) != PACKET_LENGTH:
                    continue

                samples = self._parse_packet(packet)

                # Convert and store; light filtering: drop crazy distances (e.g., > 10 m)
                with self._lock:
                    for ang, dist, conf in samples:
                        if 50 <= dist <= 10000:  # 5cm..10m
                            x,y = self._polar_to_xy(ang, dist)
                            self._points.append((x, y, int(conf)))
            except Exception as e:
                # transient errors: reopen port after a short sleep
                time.sleep(0.1)
                try:
                    if self._ser:
                        self._ser.close()
                except: pass
                self._ser = None

    def snapshot(self, max_out:int=1200) -> Tuple[List[float], List[float], List[int]]:
        """Return up to max_out latest points as 3 parallel lists (x,y,c)."""
        with self._lock:
            pts = list(self._points)[-max_out:]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cs = [p[2] for p in pts]
        return xs, ys, cs
