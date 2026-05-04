#!/usr/bin/env python3
"""Standalone hover test — bypasses backend/MAVSDK entirely.
Run with: python hover_test.py
Press Ctrl+C at any point to cut throttle immediately.
"""
import time, signal, sys
from pymavlink import mavutil

UDP = 'udpin:0.0.0.0:14553'

mav = None

def throttle(pwm):
    mav.mav.rc_channels_override_send(
        mav.target_system, mav.target_component,
        65535, 65535, pwm, 65535,
        65535, 65535, 65535, 65535
    )

def stop(*_):
    print("\n[!] Ctrl+C — cutting throttle")
    if mav:
        throttle(1100)
        time.sleep(0.5)
    sys.exit(0)

signal.signal(signal.SIGINT, stop)

print(f"Connecting to MAVProxy on {UDP} ...")
mav = mavutil.mavlink_connection(UDP)
mav.wait_heartbeat()
print(f"Heartbeat OK (sys={mav.target_system})")

print("Arming...")
mav.arducopter_arm()
mav.motors_armed_wait()
print("ARMED")

mav.set_mode(0)   # STABILIZE
time.sleep(1)
print("Mode: STABILIZE")
print("Ramping throttle — Ctrl+C to cut at any time\n")

for pwm in range(1100, 1651, 10):   # 10 PWM per step, 1s each = very gradual
    throttle(pwm)
    print(f"  {pwm} PWM")
    time.sleep(1.0)

print("Holding at 1650 — Ctrl+C to stop")
while True:
    throttle(1650)
    time.sleep(0.4)
