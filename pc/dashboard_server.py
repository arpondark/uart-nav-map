"""Flask dashboard server: receives frames and runs the realtime stitcher.

This is the entry point used by ``stitch.py`` on the PC. The PC does **not**
capture frames itself; the Jetson (``jetson/run.py``) pushes frames to the
``/upload`` endpoint. Each upload is persisted to ``data/images`` and, when
the operator has clicked **Stitch Now**, fed into the realtime stitcher so
the live map is updated immediately.

A separate ``/api/capture/start`` toggle is still exposed for development on
the PC: it captures from a local camera (USB, built-in webcam, etc.) and
streams the frames into the same pipeline. The Jetson deployment doesn't
use it.
"""

from __future__ import annotations

import json
import logging
import queue
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, render_template, request, send_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc import config
from pc.capture_controller import CaptureController, StitchController, attach
from pc.storage import StoredFrame, ensure_directories, save_frame

log = logging.getLogger("pc.dashboard")


def _put_latest(target_queue: "queue.Queue[StoredFrame]", frame: StoredFrame) -> None:
    try:
        target_queue.put_nowait(frame)
        return
    except queue.Full:
        pass
    try:
        target_queue.get_nowait()
    except queue.Empty:
        pass
    try:
        target_queue.put_nowait(frame)
    except queue.Full:
        pass


def parse_metadata(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        raise ValueError("missing metadata form field")
    metadata = json.loads(raw)
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    for key in ("lat", "lon", "time"):
        if key not in metadata:
            raise ValueError(f"metadata missing required field: {key}")
    metadata["lat"] = float(metadata["lat"])
    metadata["lon"] = float(metadata["lon"])
    metadata["time"] = str(metadata["time"])
    return metadata


def create_app(
    capture: CaptureController,
    stitch: StitchController,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent / "static"),
    )

    # ---------------------------------------------------------------
    # Dashboard + status endpoints
    # ---------------------------------------------------------------
    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/status")
    def status():
        return jsonify(
            {
                "capture": capture.status(),
                "stitch": stitch.status(),
                "image_dir": str(config.IMAGE_DIR),
            }
        )

    @app.post("/api/capture/start")
    def capture_start():
        capture.start()
        return jsonify({"ok": True, **capture.status()})

    @app.post("/api/capture/stop")
    def capture_stop():
        capture.stop()
        return jsonify({"ok": True, **capture.status()})

    @app.post("/api/stitch/start")
    def stitch_start():
        result = stitch.stitch_now()
        return jsonify({"ok": True, "result": result, **stitch.status()})

    @app.post("/api/stitch/stop")
    def stitch_stop():
        result = stitch.stitch_stop()
        return jsonify({"ok": True, **result, **stitch.status()})

    @app.get("/api/frame")
    def api_frame():
        path = request.args.get("path")
        if not path:
            return jsonify({"ok": False, "error": "missing path"}), 400
        image_path = Path(path)
        if not image_path.exists():
            return jsonify({"ok": False, "error": "not found"}), 404
        try:
            return send_file(str(image_path), mimetype="image/jpeg")
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/maps/realtime")
    def realtime_map():
        if not config.REALTIME_MAP_PATH.exists():
            return jsonify({"ok": False, "error": "realtime map not ready"}), 404
        return send_file(config.REALTIME_MAP_PATH, mimetype="image/jpeg")

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "capture": capture.status(),
                "stitch": stitch.status(),
            }
        )

    # ---------------------------------------------------------------
    # /upload — Jetson (or any external sender) drops frames here.
    # Each upload is persisted to data/images and, when the operator
    # has enabled real-time stitching, fed into the stitcher.
    # ---------------------------------------------------------------
    @app.post("/upload")
    def upload():
        uploaded = request.files.get("image")
        if uploaded is None:
            return jsonify({"ok": False, "error": "missing image file field"}), 400
        try:
            metadata = parse_metadata(request.form.get("metadata"))
            image_bytes = uploaded.read()
            if not image_bytes:
                return jsonify({"ok": False, "error": "empty image"}), 400

            frame = save_frame(image_bytes, metadata)

            # Update capture controller's "last image" so the dashboard
            # shows the most recent upload even when no local camera is
            # attached.
            capture.record_remote_frame(frame)

            # If the operator enabled Stitch Now, fold the new frame
            # into the live map immediately.
            if stitch.is_enabled():
                stitch.on_frame(frame)

            return jsonify({"ok": True, "frame": frame.to_dict()})
        except Exception as exc:
            log.exception("upload failed")
            return jsonify({"ok": False, "error": str(exc)}), 400

    return app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    ensure_directories()

    capture = CaptureController()
    stitch = StitchController()
    attach(capture, stitch)

    app = create_app(capture, stitch)

    stop_requested = False

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True
        capture.stop()
        stitch.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    host = config.DASHBOARD_HOST
    port = config.DASHBOARD_PORT
    log.info("Dashboard listening on http://%s:%s", host, port)
    log.info("Image dir:     %s", config.IMAGE_DIR)
    log.info("Realtime map:  %s", config.REALTIME_MAP_PATH)

    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        capture.stop()
        stitch.stop()

    return 0 if not stop_requested else 130


if __name__ == "__main__":
    raise SystemExit(main())