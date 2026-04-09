#!/bin/bash
# AeroDrop startup script
# Usage:
#   ./start.sh          — starts MAVProxy + backend together
#   ./start.sh --mavproxy  — MAVProxy only
#   ./start.sh --backend   — backend only

VENV="$HOME/pidrone/venv/bin/activate"
DIR="$HOME/pidrone"

source "$VENV"

case "$1" in
  --mavproxy)
    echo "[AeroDrop] Starting MAVProxy..."
    pkill -f "mavproxy.py" 2>/dev/null; sleep 1
    mavproxy.py --master=/dev/ttyAMA2 --baudrate=115200 \
      --out=udpout:127.0.0.1:14552 \
      --out=udpout:127.0.0.1:14553
    ;;

  --backend)
    echo "[AeroDrop] Starting backend..."
    cd "$DIR"
    export SIM_MODE=false
    export MAVSDK_CONNECTION="udpin://0.0.0.0:14552"
    export GUIDED_PORT=14553
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
    ;;

  --build)
    echo "[AeroDrop] Building frontend..."
    cd "$DIR/frontend"
    npm run build && cp -r dist/* "$DIR/backend/app/static/"
    echo "[AeroDrop] Frontend deployed to backend/app/static/"
    ;;

  *)
    echo "[AeroDrop] Killing stale processes..."
    pkill -f "mavproxy.py" 2>/dev/null; sleep 1
    pkill -f "uvicorn backend.main" 2>/dev/null; sleep 0.5

    echo "[AeroDrop] Starting MAVProxy..."
    mavproxy.py --master=/dev/ttyAMA2 --baudrate=115200 \
      --out=udpout:127.0.0.1:14552 \
      --out=udpout:127.0.0.1:14553 \
      --daemon

    # Wait until MAVProxy is actually forwarding on UDP 14552 (up to 15s)
    echo "[AeroDrop] Waiting for MAVProxy UDP..."
    for i in $(seq 1 15); do
      ss -ulnp | grep -q ":14552" && break
      sleep 1
      echo "  ...waiting ($i)"
    done

    echo "[AeroDrop] MAVProxy up. Starting backend..."
    cd "$DIR"
    export SIM_MODE=false
    export MAVSDK_CONNECTION="udpin://0.0.0.0:14552"
    export GUIDED_PORT=14553
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
    ;;
esac
