# Drone Dual Map System

Two-process pipeline: the Jetson grabs frames from an IP camera over RTSP
and uploads them to the PC, where the stitcher runs and a web dashboard
lets the operator start real-time stitching.

* **Jetson**: `python jetson/run.py`
  opens `rtsp://192.168.144.25:8554/main.264`, saves every frame to
  `data/jetson_images/`, and POSTs it to the PC.
* **PC**: `python stitch.py`
  hosts the dashboard on `http://0.0.0.0:5000`. The operator clicks
  **Stitch Now** to start real-time stitching; every new upload is folded
  into the live map automatically.

GPS capture is disabled for now. See `CHANGES.md` for the full update log
and instructions for re-enabling it.

## Quick start

On the PC (the receiver):

```bash
pip install -r requirements.txt
python stitch.py
```

Open the printed URL in any browser. The dashboard has:

* **Start Capture** – begin capturing from a local camera attached to
  the PC (development mode only; the Jetson is the canonical capture
  source).
* **Stitch Now** – enable real-time stitching. Every new frame the
  Jetson uploads is folded into the live map automatically.
* **Stop Stitch** – freeze the live map.

On the Jetson (the sender):

```bash
pip install -r requirements.txt
PC_UPLOAD_URL="http://<PC_IP>:5000/upload" python jetson/run.py
```

The script connects to the RTSP camera, saves a local copy of every
frame to `data/jetson_images/`, and uploads it to the PC.

`stitch_now.py` is also kept for one-shot batch stitching of images
that are already on disk on the PC.

## Architecture

```
+-------------------+        HTTP /upload         +------------------+
|  Jetson (run.py)  | --------------------------> |  PC (stitch.py)  |
|                   |                             |                  |
|  - RTSP camera    |                             |  - dashboard     |
|  - local save     |  http://<pc-ip>:5000/upload |  - stitcher      |
|  - HTTP uploader  |                             |  - /api/*        |
+-------------------+                             +------------------+
```

## Configuration

### Jetson (`jetson/config.py`)

| Variable                   | Default                                          |
| -------------------------- | ------------------------------------------------ |
| `PC_UPLOAD_URL`            | `http://127.0.0.1:5000/upload`                   |
| `PC_BASE_URL`              | derived from `PC_UPLOAD_URL`                     |
| `REQUEST_TIMEOUT_SECONDS`  | `5.0`                                            |
| `CAMERA_IP`                | `192.168.144.25`                                 |
| `RTSP_PORT`                | `8554`                                           |
| `RTSP_PATH`                | `main.264`                                       |
| `RTSP_URL`                 | `rtsp://${CAMERA_IP}:${RTSP_PORT}/${RTSP_PATH}`  |
| `CAMERA_WIDTH`             | `1280`                                           |
| `CAMERA_HEIGHT`            | `720`                                            |
| `JPEG_QUALITY`             | `85`                                             |
| `CAPTURE_INTERVAL_SECONDS` | `1.0`                                            |
| `RTSP_LATENCY_MS`          | `200`                                            |
| `LOCAL_IMAGE_DIR`          | `<repo>/data/jetson_images`                      |
| `SIYI_UDP_PORT`            | `37260` (placeholder)                            |

### PC (`pc/config.py`)

| Variable                   | Default      | Notes                                  |
| -------------------------- | ------------ | -------------------------------------- |
| `DASHBOARD_HOST`           | `0.0.0.0`    | Bind address                           |
| `DASHBOARD_PORT`           | `5000`       | HTTP port                              |
| `CAMERA_INDEX`             | `0`          | Local camera (development only)        |
| `CAMERA_WIDTH`             | `1280`       | Local capture width                    |
| `CAMERA_HEIGHT`            | `720`        | Local capture height                   |
| `JPEG_QUALITY`             | `85`         | JPEG quality for saved frames          |
| `CAPTURE_INTERVAL_SECONDS` | `1.0`        | Time between local frames              |
| `REALTIME_BUFFER_SIZE`     | `8`          | Rolling window for the live map        |
| `REALTIME_RESIZE_WIDTH`    | `640`        | Downscale width for the live map       |

## Structure

```text
stitch.py                        # PC launcher
jetson/
  run.py                         # Jetson: RTSP + upload
  rtsp_camera.py                 # Jetson: RTSP wrapper
  config.py                      # Jetson-side tunables
  capture_send.py                # legacy uploader (GPS commented)
  gps_reader.py                  # legacy GPS reader (unused)
  camera.py                      # legacy CSI / V4L2 wrapper (unused)
pc/
  dashboard_server.py            # Flask app, REST endpoints
  capture_controller.py          # capture + stitch controllers
  templates/dashboard.html       # web UI
  static/dashboard.{css,js}      # web UI assets
  storage.py                     # image/metadata IO
  realtime_stitcher.py           # fast OpenCV stitcher
  hq_stitcher.py                 # batch high-quality stitcher
  config.py                      # PC-side tunables
data/
  images/                        # frames saved by /upload
  metadata/                      # per-frame JSON metadata
  stitched/
    realtime_map.jpg             # live map
    hq_map.jpg                   # high-quality map
  jetson_images/                 # local mirror of Jetson captures
CHANGES.md                       # full changelog
```

## HTTP API

| Method | Path                 | Purpose                                |
| ------ | -------------------- | -------------------------------------- |
| GET    | `/`                  | Dashboard HTML page                    |
| GET    | `/api/status`        | Combined capture + stitch status       |
| POST   | `/api/capture/start` | Begin local camera capture             |
| POST   | `/api/capture/stop`  | Stop local camera capture              |
| POST   | `/api/stitch/start`  | Enable real-time stitching             |
| POST   | `/api/stitch/stop`   | Disable real-time stitching            |
| GET    | `/api/frame`         | Stream a captured image (`?path=...`)  |
| GET    | `/maps/realtime`     | Latest realtime stitched map           |
| GET    | `/health`            | Liveness probe                         |
| POST   | `/upload`            | External sender (form-data image + metadata JSON) |

## Flight conditions

For reliable stitching:

* Maintain 60–80% image overlap.
* Fly slowly and steadily.
* Use a downward-facing camera.
* Avoid fast rotation and heavy motion blur.
* Keep altitude and exposure as stable as possible.

## Re-enabling GPS

See `CHANGES.md` for the exact lines to uncomment.