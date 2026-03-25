"""
Smoke-test for hardware bringup — step 1.

Connects to the FC via MAVSDK + pymavlink (exactly as the backend does),
prints telemetry, and exits. Run this before starting the full backend.

Usage (from project root, venv active):
    python -m backend.drone.test_hitl

MAVProxy must already be running:
    mavproxy.py --master=/dev/ttyAMA2 --baudrate=115200 \
        --out=udpout:0.0.0.0:14552 --out=udpout:0.0.0.0:14553 --daemon
"""

import asyncio
import os

from mavsdk import System


MAVSDK_CONNECTION = os.getenv("MAVSDK_CONNECTION", "udpin://0.0.0.0:14552")


async def main():
    print(f"Connecting to {MAVSDK_CONNECTION} …")
    drone = System()
    await drone.connect(system_address=MAVSDK_CONNECTION)

    print("Waiting for connection …")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("✓ Connected!")
            break

    print("Waiting for health checks …")
    async for health in drone.telemetry.health():
        print(
            f"  is_armable={health.is_armable}  "
            f"local_pos_ok={health.is_local_position_ok}  "
            f"global_pos_ok={health.is_global_position_ok}"
        )
        break  # just one snapshot

    print("Reading telemetry …")
    async for pos in drone.telemetry.position():
        print(f"  lat={pos.latitude_deg:.6f}  lon={pos.longitude_deg:.6f}  alt={pos.relative_altitude_m:.2f} m")
        break

    async for bat in drone.telemetry.battery():
        print(f"  battery={bat.remaining_percent:.1f}%")
        break

    async for mode in drone.telemetry.flight_mode():
        print(f"  flight_mode={mode.name}")
        break

    print("\n✓ Smoke-test passed — backend/drone/ module can reach the FC.")


if __name__ == "__main__":
    asyncio.run(main())
