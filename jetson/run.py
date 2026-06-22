"""Jetson entry point: RTSP camera + HTTP uploader.

This is the only script the operator needs to run on the Jetson. It:

1. Opens the RTSP camera (default ``rtsp://192.168.144.25:8554/main.264``)
2. Saves every captured frame to ``data/jetson_images`` (this is the
   "folder where all images will be saved")
3. Uploads the same frame to the PC's ``/upload`` endpoint
4. Prints a short status line per frame

GPS is intentionally disabled; the metadata payload uses neutral
coordinates. Re-enable GPS by uncommenting the lines in
``jetson/capture_send.py`` (which already does this work).
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jetson import config
from jetson.rtsp_camera import RTSPCamera

log = logging.getLogger("jetson.run")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)


def _neutral_metadata() -> dict:
    return {
        "lat": 0.0,
        "lon": 0.0,
        "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "valid": False,
    }


def _save_locally(image_bytes: bytes, timestamp: str) -> Path:
    config.LOCAL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = timestamp.replace(":", "-").replace(".", "-").replace("+", "_")
    path = config.LOCAL_IMAGE_DIR / f"img_{safe_ts}.jpg"
    path.write_bytes(image_bytes)
    return path


def _upload_to_pc(image_bytes: bytes, metadata: dict) -> bool:
    files = {
        "image": (
            f"img_{metadata['time'].replace(':', '-').replace('.', '-')}.jpg",
            image_bytes,
            "image/jpeg",
        )
    }
    data = {"metadata": json.dumps(metadata)}
    try:
        response = requests.post(
            config.PC_UPLOAD_URL,
            files=files,
            data=data,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.warning("Upload error: %s", exc)
        return False
    if response.status_code != 200:
        log.warning("Upload failed: HTTP %s %s", response.status_code, response.text[:200])
        return False
    return True


def main() -> int:
    stop_requested = False

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    interval = max(0.0, float(config.CAPTURE_INTERVAL_SECONDS))
    sent = 0
    failed = 0
    saved = 0

    log.info("RTSP URL: %s", config.RTSP_URL)
    log.info("Saving images to: %s", config.LOCAL_IMAGE_DIR)
    log.info("Uploading to PC: %s", config.PC_UPLOAD_URL)
    log.info("Capture interval: %.2fs", interval)

    try:
        with RTSPCamera() as camera:
            while not stop_requested:
                loop_started = time.monotonic()
                metadata = _neutral_metadata()
                try:
                    image_bytes = camera.capture_jpeg()
                    local_path = _save_locally(image_bytes, metadata["time"])
                    saved += 1
                    if _upload_to_pc(image_bytes, metadata):
                        sent += 1
                        log.info(
                            "saved=%d sent=%d failed=%d file=%s",
                            saved,
                            sent,
                            failed,
                            local_path.name,
                        )
                    else:
                        failed += 1
                except Exception as exc:
                    failed += 1
                    log.warning("Capture/upload error: %s", exc)

                elapsed = time.monotonic() - loop_started
                sleep_for = max(0.0, interval - elapsed)
                if stop_requested:
                    break
                time.sleep(sleep_for)
    except Exception as exc:
        log.error("Fatal: %s", exc)
        return 1

    log.info("Capture loop stopped. saved=%d sent=%d failed=%d", saved, sent, failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())