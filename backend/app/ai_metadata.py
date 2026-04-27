import subprocess
import json
from fastapi import APIRouter

router = APIRouter()

@router.get("/camera/ai_metadata")
def ai_metadata():
    """
    Run IMX500 inference pipeline and return metadata as JSON.
    """
    try:
        # Run rpicam with a metadata-only pipeline
        result = subprocess.run([
            "rpicam-vid",
            "-t", "200",
            "--post-process-file",
            "/usr/share/rpi-camera-assets/imx500_mobilenet_ssd.json",
            "--metadata",   # ask for metadata output
            "-o", "-",       # no video, only metadata
        ], capture_output=True)

        meta = result.stdout.decode("utf-8", errors="ignore")

        return {"raw_metadata": meta}

    except Exception as e:
        return {"error": str(e)}
