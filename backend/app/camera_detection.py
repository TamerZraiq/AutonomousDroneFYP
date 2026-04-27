import json
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from subprocess import Popen, PIPE, DEVNULL
import time

router = APIRouter()

latest_detection = {"objects": [], "timestamp": 0}

def detection_reader(proc):
    global latest_detection
    for raw in proc.stderr:
        try:
            data = json.loads(raw.decode("utf-8"))
            if "objects" in data:
                latest_detection = {
                    "objects": data["objects"],
                    "timestamp": time.time()
                }
        except:
            continue

@router.get("/camera/ai_metadata")
def get_ai_metadata():
    return latest_detection
