import asyncio
import threading
import time

GPIO_PIN  = 12
CLOSED_PW = 1700   # µs — gripper closed
OPEN_PW   =  550   # µs — gripper open / drop
DROP_HOLD = 2.0    # seconds to hold open before auto-close
SETTLE_S  = 0.5    # seconds to power servo before cutting PWM


class ServoGripper:
    def __init__(self, pin: int = GPIO_PIN):
        self._pin  = pin
        self._pi   = None
        self._lock = asyncio.Lock()
        self._last_deploy: float = 0.0
        try:
            import pigpio
            pi = pigpio.pi()
            if pi.connected:
                self._pi = pi
                print(f"[ServoGripper] GPIO {pin} ready ✓")
            else:
                print("[ServoGripper] pigpiod not running — servo disabled")
        except ImportError:
            print("[ServoGripper] pigpio not installed — servo disabled")

    @property
    def available(self) -> bool:
        return self._pi is not None

    def _move(self, pw: int):
        """Send PWM pulse, then cut power after SETTLE_S so motor doesn't strain."""
        if not self._pi:
            return
        self._pi.set_servo_pulsewidth(self._pin, pw)
        threading.Timer(SETTLE_S, self._off).start()

    def _off(self):
        if self._pi:
            self._pi.set_servo_pulsewidth(self._pin, 0)

    def open(self):
        self._move(OPEN_PW)   # cut power after settle — spring holds it open

    def close(self):
        if self._pi:
            self._pi.set_servo_pulsewidth(self._pin, CLOSED_PW)  # hold power to grip

    async def drop(self):
        """Open, hold for DROP_HOLD seconds, close. Non-reentrant."""
        async with self._lock:
            self.open()
            await asyncio.sleep(DROP_HOLD)
            self.close()
            self._last_deploy = time.time()

    def cooldown_ok(self, seconds: float = 5.0) -> bool:
        return (time.time() - self._last_deploy) > seconds

    def shutdown(self):
        if self._pi:
            self._pi.set_servo_pulsewidth(self._pin, 0)
            self._pi.stop()
