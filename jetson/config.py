"""Jetson-side configuration."""

import os
from pathlib import Path


# ============================================================
# NETWORK
# ============================================================
# PC stitcher endpoint (default localhost; override for the real PC).
PC_UPLOAD_URL = os.getenv("PC_UPLOAD_URL", "http://127.0.0.1:5000/upload")
PC_BASE_URL = os.getenv("PC_BASE_URL", PC_UPLOAD_URL.rsplit("/upload", 1)[0])
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0"))

# ============================================================
# CAMERA (RTSP)
# ============================================================
# IP camera used in place of the Pi / CSI camera.
CAMERA_IP = os.getenv("CAMERA_IP", "192.168.144.25")
RTSP_PORT = int(os.getenv("RTSP_PORT", "8554"))
RTSP_PATH = os.getenv("RTSP_PATH", "main.264")
RTSP_URL = os.getenv(
    "RTSP_URL",
    f"rtsp://{CAMERA_IP}:{RTSP_PORT}/{RTSP_PATH}",
)

# Used as a fallback if RTSP fails to open.
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "1280"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "720"))
CAMERA_FPS = int(os.getenv("CAMERA_FPS", "30"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "85"))

CAPTURE_INTERVAL_SECONDS = float(os.getenv("CAPTURE_INTERVAL_SECONDS", "1.0"))

# How many frames the RTSP decoder keeps in the GStreamer queue.
RTSP_LATENCY_MS = int(os.getenv("RTSP_LATENCY_MS", "200"))

# ============================================================
# LOCAL STORAGE
# ============================================================
# Local images folder (Jetson-side) that backs the uploader.
LOCAL_IMAGE_DIR = Path(
    os.getenv(
        "LOCAL_IMAGE_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "jetson_images"),
    )
).resolve()

# ============================================================
# SIYI TELEMETRY (placeholder; not wired in yet)
# ============================================================
SIYI_UDP_PORT = int(os.getenv("SIYI_UDP_PORT", "37260"))

# ============================================================
# GPS (temporarily disabled)
# ============================================================
# GPS_SERIAL_PORT = os.getenv("GPS_SERIAL_PORT", "/dev/ttyUSB0")
# GPS_BAUDRATE = int(os.getenv("GPS_BAUDRATE", "9600"))
# GPS_TIMEOUT_SECONDS = float(os.getenv("GPS_TIMEOUT_SECONDS", "1.0"))

# Used until the first valid GPS fix arrives.
FALLBACK_LAT = float(os.getenv("FALLBACK_LAT", "0.0"))
FALLBACK_LON = float(os.getenv("FALLBACK_LON", "0.0"))