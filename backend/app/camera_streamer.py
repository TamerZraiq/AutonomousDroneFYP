import subprocess
import json
import threading
import time
import numpy as np
import cv2
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

# Global shared detection buffer
latest_detection = {"objects": [], "timestamp": 0}


# ================================
#   READ METADATA (Background)
# ================================
def read_ai_metadata(proc):
    global latest_detection
    for line in proc.stderr:
        try:
            packet = json.loads(line.decode("utf-8"))
            if "objects" in packet:
                latest_detection = {
                    "objects": packet["objects"],
                    "timestamp": time.time()
                }
        except:
            continue


# ================================
#   FRAME GENERATOR
# ================================
def frame_generator():

    proc = subprocess.Popen([
        "rpicam-vid",
        "-t", "0",
        "--inline",
        "--codec", "mjpeg",
        "--framerate", "15",
        "--width", "640",
        "--height", "480",
        "--post-process-file", "/usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json",
        "--metadata", "--metadata-format", "json",
        "-o", "-"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)

    # Start metadata thread
    threading.Thread(target=read_ai_metadata, args=(proc,), daemon=True).start()

    buffer = b""
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"

    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        buffer += chunk

        start = buffer.find(b"\xff\xd8")
        end = buffer.find(b"\xff\xd9")

        if start != -1 and end != -1:
            jpg = buffer[start:end+2]
            buffer = buffer[end+2:]

            frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)

            # Draw detections
            for obj in latest_detection["objects"]:
                x = int(obj["x"] * frame.shape[1])
                y = int(obj["y"] * frame.shape[0])
                w = int(obj["width"] * frame.shape[1])
                h = int(obj["height"] * frame.shape[0])

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0,255,0), 2)
                cv2.putText(frame, obj["class"], (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

            ok, encoded = cv2.imencode(".jpg", frame)
            yield boundary + encoded.tobytes() + b"\r\n"


# ================================
#   STREAM ENDPOINT
# ================================
@router.get("/camera/stream")
def stream():
    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ================================
#   AI METADATA ENDPOINT
# ================================
@router.get("/camera/ai_metadata")
def ai_metadata():
    return latest_detection
