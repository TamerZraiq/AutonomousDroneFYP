#!/usr/bin/env python3
import serial, struct, csv, time
from enum import Enum

SERIAL_PORT = "/dev/ttyAMA0"
BAUD = 230400
PACKET_LENGTH = 47
MEASUREMENT_LENGTH = 12
MESSAGE_FORMAT = "<xBHH" + "HB" * MEASUREMENT_LENGTH + "HHB"

State = Enum("State", ["SYNC0", "SYNC1", "SYNC2", "LOCKED"])
outfile = f"lidar_log_{int(time.time())}.csv"

def parse_lidar_data(data):
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

def main():
    lidar = serial.Serial(SERIAL_PORT, BAUD, timeout=0.5)
    measurements, data, state = [], b"", State.SYNC0
    count = 0

    with open(outfile, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["angle_deg", "distance_mm", "confidence"])
        print(f"Logging to {outfile} ... Press Ctrl+C to stop.")
        try:
            while True:
                if state == State.SYNC0:
                    data = b''
                    if lidar.read() == b'\x54':
                        data = b'\x54'
                        state = State.SYNC1
                elif state == State.SYNC1:
                    if lidar.read() == b'\x2C':
                        data += b'\x2C'
                        state = State.SYNC2
                    else:
                        state = State.SYNC0
                elif state == State.SYNC2:
                    data += lidar.read(PACKET_LENGTH - 2)
                    if len(data) != PACKET_LENGTH:
                        state = State.SYNC0
                        continue
                    for a, d, c in parse_lidar_data(data):
                        writer.writerow([a, d, c])
                    count += 1
                    if count % 50 == 0:
                        print(f"{count} packets logged...", end="\r")
                    state = State.SYNC0
        except KeyboardInterrupt:
            print(f"\nStopped. Total packets: {count}")
            lidar.close()

if __name__ == "__main__":
    main()
