import asyncio
from enum import Enum


class State(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    TAKEOFF = "TAKEOFF"
    MISSION = "MISSION"
    RTL = "RTL"
    LANDED = "LANDED"
    EMERGENCY = "EMERGENCY"


AIRBORNE = {State.TAKEOFF, State.MISSION, State.RTL}

# Valid transitions: state -> set of states reachable from it
TRANSITIONS = {
    State.IDLE:      {State.ARMED},
    State.ARMED:     {State.TAKEOFF, State.IDLE, State.EMERGENCY},
    State.TAKEOFF:   {State.ARMED, State.MISSION, State.RTL, State.EMERGENCY},
    State.MISSION:   {State.RTL, State.EMERGENCY},
    State.RTL:       {State.LANDED, State.EMERGENCY},
    State.LANDED:    {State.IDLE, State.EMERGENCY},
    State.EMERGENCY: {State.IDLE},
}


class StateMachine:
    def __init__(self):
        self._state = State.IDLE
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def transition(self, to: State) -> bool:
        async with self._lock:
            if to in TRANSITIONS.get(self._state, set()):
                self._state = to
                return True
            return False

    async def trigger_emergency(self):
        async with self._lock:
            self._state = State.EMERGENCY

    def is_airborne(self) -> bool:
        return self._state in AIRBORNE
