"""Flask receiver and process supervisor for the PC mapping system."""

import json
import queue
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pc import config
from pc.hq_stitcher import HQStitcher
from pc.realtime_stitcher import RealtimeStitcher
from pc.storage import StoredFrame, ensure_directories, save_frame
from pc.viewer import MapViewer


def put_latest(target_queue: "queue.Queue[StoredFrame]", frame: StoredFrame) -> None:
    """Put without letting slow consumers block the upload path."""

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
    realtime_queue: "queue.Queue[StoredFrame]",
    hq_queue: "queue.Queue[StoredFrame]",
    viewer_queue: "queue.Queue[StoredFrame]",
) -> Flask:
    app = Flask(__name__)

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
            put_latest(realtime_queue, frame)
            put_latest(hq_queue, frame)
            put_latest(viewer_queue, frame)

            return jsonify({"ok": True, "frame": frame.to_dict()})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "realtime_queue": realtime_queue.qsize(),
                "hq_queue": hq_queue.qsize(),
                "viewer_queue": viewer_queue.qsize(),
                "realtime_map": config.REALTIME_MAP_PATH.exists(),
                "hq_map": config.HQ_MAP_PATH.exists(),
            }
        )

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

    return app


def main() -> int:
    ensure_directories()

    realtime_queue: "queue.Queue[StoredFrame]" = queue.Queue(maxsize=config.QUEUE_MAX_SIZE)
    hq_queue: "queue.Queue[StoredFrame]" = queue.Queue(maxsize=config.QUEUE_MAX_SIZE)
    viewer_queue: "queue.Queue[StoredFrame]" = queue.Queue(maxsize=config.QUEUE_MAX_SIZE)

    realtime_worker = RealtimeStitcher(realtime_queue)
    hq_worker = HQStitcher(hq_queue)
    viewer = MapViewer(viewer_queue) if config.VIEWER_ENABLED else None

    workers = [realtime_worker, hq_worker]
    if viewer is not None:
        workers.append(viewer)

    stop_requested = False

    def request_stop(signum, frame) -> None:
        nonlocal stop_requested
        stop_requested = True
        for worker in workers:
            worker.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    for worker in workers:
        worker.start()

    app = create_app(realtime_queue, hq_queue, viewer_queue)
    print(f"PC receiver listening on http://{config.SERVER_HOST}:{config.SERVER_PORT}")
    print(f"Raw images: {config.IMAGE_DIR}")
    print(f"Metadata: {config.METADATA_DIR}")
    print(f"Maps: {config.STITCHED_DIR}")

    try:
        app.run(
            host=config.SERVER_HOST,
            port=config.SERVER_PORT,
            threaded=True,
            use_reloader=False,
        )
    finally:
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=2.0)

    return 0 if not stop_requested else 130


if __name__ == "__main__":
    raise SystemExit(main())
