from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import subprocess

router = APIRouter()

def frame_generator():
    cmd = [
        "/usr/bin/rpicam-vid",
        "-t", "0",                 # endless stream
        "--codec", "mjpeg",
        "--inline",
        "--framerate", "15",
        "--width", "640",
        "--height", "480",
        "-o", "-"                  # output to stdout
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"

    buffer = b""

    try:
        while True:
            chunk = proc.stdout.read(4096)

            if not chunk:
                break

            buffer += chunk

            # JPEG images start with FFD8 and end with FFD9
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9")

            if start != -1 and end != -1:
                jpeg = buffer[start:end + 2]
                buffer = buffer[end + 2:]

                yield boundary + jpeg + b"\r\n"

    finally:
        proc.kill()


@router.get("/camera/stream")
def stream():
    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
