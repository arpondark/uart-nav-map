"""Jetson-side configuration."""

import os


PC_UPLOAD_URL = os.getenv("PC_UPLOAD_URL", "http://127.0.0.1:5000/upload")

CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "1280"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "720"))
CAMERA_FPS = int(os.getenv("CAMERA_FPS", "30"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "90"))

CAPTURE_INTERVAL_SECONDS = float(os.getenv("CAPTURE_INTERVAL_SECONDS", "1.0"))

GPS_SERIAL_PORT = os.getenv("GPS_SERIAL_PORT", "/dev/ttyUSB0")
GPS_BAUDRATE = int(os.getenv("GPS_BAUDRATE", "9600"))
GPS_TIMEOUT_SECONDS = float(os.getenv("GPS_TIMEOUT_SECONDS", "1.0"))

REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0"))

# Used until the first valid GPS fix arrives.
FALLBACK_LAT = float(os.getenv("FALLBACK_LAT", "0.0"))
FALLBACK_LON = float(os.getenv("FALLBACK_LON", "0.0"))
