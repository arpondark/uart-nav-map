"""PC-side configuration."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
IMAGE_DIR = DATA_DIR / "images"
METADATA_DIR = DATA_DIR / "metadata"
STITCHED_DIR = DATA_DIR / "stitched"

REALTIME_MAP_PATH = STITCHED_DIR / "realtime_map.jpg"
HQ_MAP_PATH = STITCHED_DIR / "hq_map.jpg"

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))

REALTIME_BUFFER_SIZE = int(os.getenv("REALTIME_BUFFER_SIZE", "8"))
REALTIME_RESIZE_WIDTH = int(os.getenv("REALTIME_RESIZE_WIDTH", "640"))

HQ_BATCH_SIZE = int(os.getenv("HQ_BATCH_SIZE", "25"))
HQ_MIN_IMAGES = int(os.getenv("HQ_MIN_IMAGES", "8"))
HQ_MAX_IMAGES = int(os.getenv("HQ_MAX_IMAGES", "50"))
HQ_TRIGGER_SECONDS = float(os.getenv("HQ_TRIGGER_SECONDS", "60.0"))

VIEWER_ENABLED = os.getenv("VIEWER_ENABLED", "1").lower() not in {"0", "false", "no"}
VIEWER_REFRESH_MS = int(os.getenv("VIEWER_REFRESH_MS", "100"))

QUEUE_MAX_SIZE = int(os.getenv("QUEUE_MAX_SIZE", "200"))
