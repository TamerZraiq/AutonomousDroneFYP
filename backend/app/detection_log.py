"""
DetectionLog — thread-safe list of objects seen during a mission.

Each entry stores:
  - object class (e.g. "person")
  - confidence score
  - NED position at time of detection
  - timestamp
  - JPEG frame bytes captured at detection moment (may be None)
"""

import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Detection:
    object_class: str
    confidence:   float
    north:        float
    east:         float
    timestamp:    float
    frame_jpg:    Optional[bytes] = None   # raw JPEG bytes, None if not captured


class DetectionLog:
    def __init__(self):
        self._entries: List[Detection] = []
        self._lock = threading.Lock()

    def add(self,
            object_class: str,
            confidence: float,
            north: float,
            east: float,
            frame_jpg: Optional[bytes] = None):
        entry = Detection(
            object_class=object_class,
            confidence=confidence,
            north=north,
            east=east,
            timestamp=time.time(),
            frame_jpg=frame_jpg,
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def all(self) -> List[Detection]:
        with self._lock:
            return list(self._entries)

    def as_dicts(self) -> list:
        """Serialisable form (no frame bytes) for telemetry WS / REST."""
        with self._lock:
            return [
                {
                    "object_class": e.object_class,
                    "confidence":   round(e.confidence, 3),
                    "north":        round(e.north, 3),
                    "east":         round(e.east, 3),
                    "timestamp":    e.timestamp,
                    "has_frame":    e.frame_jpg is not None,
                }
                for e in self._entries
            ]

    def clear(self):
        with self._lock:
            self._entries.clear()

    def __len__(self):
        with self._lock:
            return len(self._entries)
