"""Flask dashboard server: receives frames, runs realtime + HQ stitching.

The dashboard exposes every stitch mode as a button:

* **Start / Stop Capture** – start the local camera (development mode
  only; the Jetson is the canonical capture source in production).
* **Stitch Realtime** – enable the fast low-resolution stitcher. Every
  new uploaded frame is folded into the live map immediately.
* **Stitch HQ** – enable the high-quality batch stitcher. Frames are
  collected into a window and a full OpenCV stitch runs every
  ``HQ_BATCH_SIZE`` frames or every ``HQ_TRIGGER_SECONDS``.
* **Stitch All** – start both modes at once.
* **Stitch Stop** – stop whichever modes are running.

``/upload`` accepts frames from the Jetson (``jetson/run.py``). Each
upload is persisted to ``data/images`` and forwarded to whichever
stitchers are enabled.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, render_template, request, send_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc import config
from pc.capture_controller import (
    CaptureController,
    HQController,
    StitchController,
    attach,
    attach_hq,
)
from pc.storage import ensure_directories, save_frame

log = logging.getLogger("pc.dashboard")


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
    hq: HQController,
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
                "hq": hq.status(),
                "image_dir": str(config.IMAGE_DIR),
                "realtime_map": str(config.REALTIME_MAP_PATH),
                "hq_map": str(config.HQ_MAP_PATH),
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

    @app.post("/api/hq/start")
    def hq_start():
        result = hq.start()
        return jsonify({"ok": True, **result})

    @app.post("/api/hq/stop")
    def hq_stop():
        result = hq.stop()
        return jsonify({"ok": True, **result})

    @app.post("/api/all/start")
    def all_start():
        stitch_result = stitch.stitch_now()
        hq_result = hq.start()
        return jsonify(
            {
                "ok": True,
                "stitch": stitch_result,
                "hq": hq_result,
                "stitch_status": stitch.status(),
                "hq_status": hq.status(),
            }
        )

    @app.post("/api/all/stop")
    def all_stop():
        stitch_result = stitch.stitch_stop()
        hq_result = hq.stop()
        return jsonify(
            {
                "ok": True,
                "stitch": stitch_result,
                "hq": hq_result,
                "stitch_status": stitch.status(),
                "hq_status": hq.status(),
            }
        )

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

    @app.get("/maps/hq")
    def hq_map():
        if not config.HQ_MAP_PATH.exists():
            return jsonify({"ok": False, "error": "HQ map not ready"}), 404
        return send_file(config.HQ_MAP_PATH, mimetype="image/jpeg")

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "capture": capture.status(),
                "stitch": stitch.status(),
                "hq": hq.status(),
            }
        )

    # ---------------------------------------------------------------
    # /upload — Jetson (or any external sender) drops frames here.
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

            capture.record_remote_frame(frame)

            if stitch.is_enabled():
                stitch.on_frame(frame)
            if hq.is_enabled():
                hq.on_frame(frame)

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
    hq = HQController()
    attach(capture, stitch)
    attach_hq(capture, hq)

    app = create_app(capture, stitch, hq)

    stop_requested = False

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True
        capture.stop()
        stitch.stop()
        hq.shutdown()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    host = config.DASHBOARD_HOST
    port = config.DASHBOARD_PORT
    log.info("Dashboard listening on http://%s:%s", host, port)
    log.info("Image dir:     %s", config.IMAGE_DIR)
    log.info("Realtime map:  %s", config.REALTIME_MAP_PATH)
    log.info("HQ map:        %s", config.HQ_MAP_PATH)

    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        capture.stop()
        stitch.stop()
        hq.shutdown()

    return 0 if not stop_requested else 130


if __name__ == "__main__":
    raise SystemExit(main())