# Update: Jetson RTSP capture + PC dashboard

This update splits the system into two single-process deployments:

* **Jetson** runs `jetson/run.py` — opens the IP camera over RTSP, saves
  every frame locally, and POSTs it to the PC's dashboard server.
* **PC** runs `stitch.py` — opens a web dashboard, receives uploaded
  frames, and stitches them in real time when the operator clicks
  *Stitch Now*.

GPS capture remains disabled for now.

## What changed

### New architecture

```
+-------------------+        HTTP /upload         +------------------+
|  Jetson (run.py)  | --------------------------> |  PC (stitch.py)  |
|                   |                             |                  |
|  - RTSP camera    |                             |  - dashboard     |
|  - local save     |  http://<pc-ip>:5000/upload |  - stitcher      |
|  - HTTP uploader  |                             |  - /api/*        |
+-------------------+                             +------------------+
```

### Jetson side

* **NEW** `jetson/run.py` — captures frames from the IP camera at
  `rtsp://192.168.144.25:8554/main.264` (configurable via
  `RTSP_URL` / `CAMERA_IP` / `RTSP_PORT` / `RTSP_PATH`), saves them to
  `data/jetson_images/`, and POSTs each frame to the PC's `/upload`
  endpoint.
* **NEW** `jetson/rtsp_camera.py` — synchronous RTSP camera wrapper
  with GStreamer pipeline and libav fallback.
* `jetson/config.py` — adds the RTSP, network, and SIYI telemetry
  configuration. The PC URL is set with `PC_UPLOAD_URL` (default
  `http://127.0.0.1:5000/upload`).
* `jetson/capture_send.py` is kept for reference (GPS removed,
  neutral metadata used).

### PC side

* `stitch.py` (project root) is the PC-side launcher. It opens the
  dashboard, which shows the latest uploaded frame and the live
  stitched map.
* `pc/dashboard_server.py` now exposes:
  * `GET /` — dashboard HTML
  * `GET /api/status` — combined capture + stitch state
  * `POST /api/capture/start` / `stop` — only useful when a local
    camera is attached to the PC (e.g. for development).
  * `POST /api/stitch/start` / `stop` — enable/disable real-time
    stitching (alias *Stitch Now*).
  * `GET /maps/realtime` — stream the latest stitched map.
  * `POST /upload` — receive frames from the Jetson; each upload is
    persisted to `data/images` and, when stitching is enabled, folded
    into the live map automatically.
* `pc/capture_controller.py` adds `record_remote_frame()` so the
  dashboard reflects Jetson uploads even when no local camera is
  attached.
* `pc/templates/dashboard.html` + `pc/static/dashboard.{css,js}` are
  unchanged from the previous version; the UI is the same.

### Configuration

`jetson/config.py` reads the following environment variables (all
optional, with sensible defaults):

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

The PC side uses `pc/config.py` and supports `DASHBOARD_HOST`,
`DASHBOARD_PORT`, and the stitcher tunables from the previous version.

## How to use it

### On the Jetson

```bash
PC_UPLOAD_URL="http://<PC_IP>:5000/upload" \
CAMERA_IP=192.168.144.25 \
python jetson/run.py
```

The script:

1. Connects to the RTSP camera (or falls back to the local V4L2
   device).
2. Saves a copy of every frame to `data/jetson_images/`.
3. Uploads the frame to the PC and prints a one-line status.

### On the PC

```bash
python stitch.py
```

The terminal prints the dashboard URL, e.g.
`http://192.168.0.42:5000`. Open it in any browser. The dashboard has:

* **Start Capture** — only relevant if a local camera is attached
  (development mode).
* **Stitch Now** — enables real-time stitching; every new upload is
  folded into the live map automatically.
* **Stop Stitch** — freezes the live map.

The page also shows the latest uploaded frame, the live stitched map,
the buffer size, and the most recent stitch time.

## Re-enabling GPS

GPS code in `jetson/capture_send.py` is preserved as comments. To
re-enable, uncomment the `GPSReader` import and the `gps.start()` /
`gps.get_fix().to_metadata()` lines, and supply valid `GPS_SERIAL_PORT`
/ `GPS_BAUDRATE` values in `jetson/config.py`.

## File map

```
jetson/
  run.py                 # NEW: RTSP capture + uploader
  rtsp_camera.py         # NEW: RTSP wrapper
  config.py              # RTSP + network + SIYI settings
  capture_send.py        # legacy single-process uploader (GPS commented)
  gps_reader.py          # legacy GPS reader (unused)
  camera.py              # legacy CSI / V4L2 wrapper (unused)
pc/
  dashboard_server.py    # /upload + dashboard endpoints
  capture_controller.py  # capture + stitch controllers
  templates/dashboard.html
  static/dashboard.{css,js}
  storage.py
  realtime_stitcher.py
  hq_stitcher.py
  config.py              # dashboard + stitch tunables
stitch.py                # PC launcher
data/
  images/                # frames saved by /upload
  metadata/              # per-frame JSON
  stitched/              # realtime_map.jpg, hq_map.jpg
  jetson_images/         # local mirror of the Jetson captures
README.md                # rewritten for the new architecture
CHANGES.md               # this file
```