"""Capture images and GPS fixes on the Jetson, then POST them to the PC."""

import json
import signal
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jetson import config
from jetson.camera import Camera
from jetson.gps_reader import GPSReader


def post_frame(image_bytes: bytes, metadata: dict) -> bool:
    files = {
        "image": (
            f"img_{metadata['time'].replace(':', '-').replace('.', '-')}.jpg",
            image_bytes,
            "image/jpeg",
        )
    }
    data = {"metadata": json.dumps(metadata)}

    response = requests.post(
        config.PC_UPLOAD_URL,
        files=files,
        data=data,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        print(f"Upload failed: HTTP {response.status_code} {response.text[:200]}")
        return False
    return True


def main() -> int:
    stop_requested = False

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    gps = GPSReader()
    gps.start()

    sent_count = 0
    failed_count = 0

    try:
        with Camera() as camera:
            print(f"Sending frames to {config.PC_UPLOAD_URL}")
            while not stop_requested:
                loop_started = time.monotonic()
                try:
                    image_bytes = camera.capture_jpeg()
                    metadata = gps.get_fix().to_metadata()

                    if post_frame(image_bytes, metadata):
                        sent_count += 1
                        print(
                            f"sent={sent_count} failed={failed_count} "
                            f"lat={metadata['lat']:.7f} lon={metadata['lon']:.7f} "
                            f"valid_gps={metadata['valid']}"
                        )
                    else:
                        failed_count += 1
                except Exception as exc:
                    failed_count += 1
                    print(f"Capture/upload error: {exc}")

                elapsed = time.monotonic() - loop_started
                time.sleep(max(0.0, config.CAPTURE_INTERVAL_SECONDS - elapsed))
    finally:
        gps.stop()

    print("Capture loop stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
