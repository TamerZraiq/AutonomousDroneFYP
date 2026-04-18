import sys
import threading
import time
import numpy as np
import cv2
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

# picamera2 is a system package; append its path so it's importable from the venv
# (cv2 lives in the venv and will still be found first)
sys.path.append("/usr/lib/python3/dist-packages")

router = APIRouter()

latest_detection = {"objects": [], "timestamp": 0}
latest_frame: bytes | None = None
_frame_lock = threading.Lock()

_MODEL = "/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk"

# COCO 80-class labels (matches mobilenet_ssd class IDs)
_COCO_LABELS = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
    "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
    "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
    "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
    "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair",
    "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
    "remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator",
    "book","clock","vase","scissors","teddy bear","hair drier","toothbrush",
]


def _camera_loop():
    global latest_detection, latest_frame

    while True:
        picam2 = None
        try:
            from picamera2 import Picamera2
            from picamera2.devices.imx500 import IMX500

            imx500 = IMX500(_MODEL)
            picam2 = Picamera2(imx500.camera_num)

            config = picam2.create_preview_configuration(
                main={"size": (640, 480), "format": "RGB888"},
                controls={"FrameRate": 15},
            )
            picam2.configure(config)
            imx500.show_network_fw_progress_bar()
            picam2.start()
            print("[camera_streamer] picamera2 + IMX500 ready", flush=True)

            while True:
                req = picam2.capture_request()
                try:
                    frame_rgb = req.make_array("main")
                    metadata  = req.get_metadata()

                    np_outputs = imx500.get_outputs(metadata, add_batch=True)
                    if np_outputs is not None:
                        objects = _parse(np_outputs)
                        if objects:
                            latest_detection = {"objects": objects, "timestamp": time.time()}

                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    for obj in latest_detection.get("objects", []):
                        _draw(frame_bgr, obj)

                    ok, buf = cv2.imencode(".jpg", frame_bgr)
                    if ok:
                        with _frame_lock:
                            latest_frame = buf.tobytes()
                finally:
                    req.release()

        except Exception as e:
            print(f"[camera_streamer] error: {e}", flush=True)
        finally:
            if picam2:
                try:
                    picam2.stop()
                except Exception:
                    pass

        print("[camera_streamer] restarting in 3 s", flush=True)
        time.sleep(3)


def _parse(np_outputs, threshold=0.3):
    objects = []
    try:
        boxes   = np_outputs[0][0]   # [N, 4]  y0,x0,y1,x1 normalised
        scores  = np_outputs[1][0]   # [N]
        classes = np_outputs[2][0]   # [N]
        for box, score, cls in zip(boxes, scores, classes):
            score = float(score)
            if score < threshold:
                continue
            y0, x0, y1, x1 = [max(0.0, min(1.0, float(v))) for v in box]
            label = _COCO_LABELS[int(cls)] if int(cls) < len(_COCO_LABELS) else str(int(cls))
            objects.append({
                "class":  label,
                "score":  round(score, 4),
                "x":      round(x0, 4),
                "y":      round(y0, 4),
                "width":  round(x1 - x0, 4),
                "height": round(y1 - y0, 4),
            })
    except Exception as e:
        print(f"[camera_streamer] parse error: {e}", flush=True)
    return objects


def _draw(frame, obj):
    h, w = frame.shape[:2]
    x  = int(obj["x"]      * w)
    y  = int(obj["y"]      * h)
    bw = int(obj["width"]  * w)
    bh = int(obj["height"] * h)
    cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
    cv2.putText(frame, f"{obj['class']} {obj['score']:.0%}", (x, max(10, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


threading.Thread(target=_camera_loop, daemon=True).start()


@router.get("/camera/stream")
def stream():
    def _generate():
        while True:
            with _frame_lock:
                frame = latest_frame
            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame +
                    b"\r\n"
                )
            time.sleep(1 / 15)

    return StreamingResponse(
        _generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/camera/ai_metadata")
def ai_metadata():
    return latest_detection
