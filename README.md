# Drone Dual Map System

Two-process pipeline with a single web dashboard that exposes every
stitch mode as a button.

* **Jetson** runs `jetson/run.py` — opens the IP camera at
  `rtsp://192.168.144.25:8554/main.264`, saves every frame locally to
  `data/jetson_images/`, and POSTs it to the PC.
* **PC** runs `pc/run.py` — hosts the web dashboard on
  `http://0.0.0.0:5000`. The operator clicks **Stitch Realtime**,
  **Stitch HQ**, or **Stitch All**; every new upload is folded into
  the appropriate map automatically.

GPS capture is disabled for now. See `CHANGES.md` for the full update
log and instructions for re-enabling it.

## What to run

* To get the web dashboard on the PC: `python pc/run.py`
  (or `python stitch.py` — same thing).
* To start the Jetson sender: `python jetson/run.py`

That's all. No other scripts to run.

## Quick start

```bash
# PC (the receiver / dashboard)
pip install -r requirements.txt
python pc/run.py

# Jetson (the sender)
pip install -r requirements.txt
PC_UPLOAD_URL="http://<PC_IP>:5000/upload" python jetson/run.py
```

Open the printed dashboard URL in any browser.

## Dashboard buttons

| Button              | What it does                                                   |
| ------------------- | -------------------------------------------------------------- |
| Start / Stop Capture | Local PC camera (development only)                             |
| **Stitch Realtime** | Fast low-res preview, every new frame updates the live map     |
| **Stitch HQ**       | High-quality batch, runs every N frames or T seconds           |
| **Stitch All**      | Starts both Realtime and HQ                                    |
| Stop All            | Stops whichever stitch modes are running                       |

The dashboard also shows three previews: **Latest Frame**, **Realtime
Map**, **HQ Map**, plus the buffer size, last stitch time, FPS, and HQ
CUDA availability.

## Architecture

```
+-------------------+        HTTP /upload         +------------------+
|  Jetson (run.py)  | --------------------------> |  PC (run.py)     |
|                   |                             |                  |
|  - RTSP camera    |                             |  - dashboard     |
|  - local save     |  http://<pc-ip>:5000/upload |  - realtime      |
|  - HTTP uploader  |                             |  - HQ stitcher   |
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
| `HQ_BATCH_SIZE`            | `25`         | Frames between HQ re-stitches          |
| `HQ_TRIGGER_SECONDS`       | `60.0`       | Max age between HQ re-stitches         |
| `HQ_MIN_IMAGES`            | `8`          | Minimum frames before HQ starts        |
| `HQ_MAX_IMAGES`            | `50`         | Maximum window size for HQ             |

## Structure

```text
pc/                                # everything the PC needs
  run.py                           # single entry point
  dashboard_server.py              # Flask app + REST endpoints
  capture_controller.py            # CaptureController, StitchController, HQController
  realtime_stitcher.py             # fast OpenCV stitcher
  hq_stitcher.py                   # batch HQ stitcher
  storage.py                       # image/metadata IO
  config.py                        # PC-side tunables
  templates/dashboard.html         # web UI
  static/dashboard.{css,js}        # web UI assets
jetson/                            # everything the Jetson needs
  run.py                           # single entry point
  rtsp_camera.py                   # RTSP wrapper
  config.py                        # Jetson-side tunables
stitch.py                          # top-level alias for pc/run.py
data/
  images/                          # frames saved by /upload
  metadata/                        # per-frame JSON metadata
  stitched/
    realtime_map.jpg               # output of Stitch Realtime
    hq_map.jpg                     # output of Stitch HQ
  jetson_images/                   # local mirror of the Jetson captures
README.md
CHANGES.md                         # full changelog
```

## HTTP API

| Method | Path                 | Purpose                                |
| ------ | -------------------- | -------------------------------------- |
| GET    | `/`                  | Dashboard HTML page                    |
| GET    | `/api/status`        | Combined capture + realtime + HQ state |
| POST   | `/api/capture/start` | Begin local camera capture             |
| POST   | `/api/capture/stop`  | Stop local camera capture              |
| POST   | `/api/stitch/start`  | Enable realtime stitching              |
| POST   | `/api/stitch/stop`   | Disable realtime stitching             |
| POST   | `/api/hq/start`      | Enable HQ stitching                    |
| POST   | `/api/hq/stop`       | Disable HQ stitching                   |
| POST   | `/api/all/start`     | Enable realtime + HQ                   |
| POST   | `/api/all/stop`      | Disable realtime + HQ                  |
| GET    | `/api/frame`         | Stream a captured image (`?path=...`)  |
| GET    | `/maps/realtime`     | Latest realtime stitched map           |
| GET    | `/maps/hq`           | Latest HQ stitched map                 |
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

See `CHANGES.md` for the exact lines to add.