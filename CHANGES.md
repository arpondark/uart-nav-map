# Final architecture

The system is split into two single-process deployments with a single
web dashboard that exposes every stitch mode as a button.

## What file to run to get the web dashboard

**On the PC:** `python pc/run.py`
(or `python stitch.py` — it just delegates to `pc/run.py`)

**On the Jetson:** `python jetson/run.py`

That's it. The PC's `pc/run.py` brings up the dashboard, the `/upload`
endpoint, the realtime stitcher, and the high-quality stitcher all at
once. The Jetson's `jetson/run.py` opens the RTSP camera, saves frames
locally, and uploads them to the PC.

## Dashboard buttons (all stitch options in one place)

| Button              | Endpoint                | What it does                                    |
| ------------------- | ----------------------- | ----------------------------------------------- |
| Start / Stop Capture | `/api/capture/start|stop` | Local PC camera (dev only); Jetson is canonical |
| **Stitch Realtime** | `/api/stitch/start`     | Fast low-res preview, every-frame update        |
| **Stitch HQ**       | `/api/hq/start`         | High-quality batch, every N frames or T seconds |
| **Stitch All**      | `/api/all/start`        | Starts both Realtime and HQ                     |
| Stop All            | `/api/all/stop`         | Stops whichever modes are running               |

The dashboard also shows three previews: **Latest Frame**, **Realtime
Map**, **HQ Map**, plus the buffer size, last stitch time, FPS, and HQ
CUDA availability.

## Final file map

### PC side (run `pc/run.py`)

```
pc/
  run.py                 # PC entry point — single command to start everything
  dashboard_server.py    # Flask app: /upload + all stitch API endpoints
  capture_controller.py  # CaptureController / StitchController / HQController
  templates/dashboard.html
  static/dashboard.{css,js}
  storage.py             # image/metadata IO
  realtime_stitcher.py   # fast OpenCV stitcher (used by StitchController)
  hq_stitcher.py         # batch high-quality stitcher (used by HQController)
  config.py              # PC-side tunables
stitch.py                # top-level alias for pc/run.py
```

### Jetson side (run `jetson/run.py`)

```
jetson/
  run.py                 # Jetson entry point: RTSP + local save + upload
  rtsp_camera.py         # RTSP camera wrapper (GStreamer + libav fallback)
  config.py              # RTSP / network / SIYI tunables
```

### Data folders

```
data/
  images/                # frames saved by /upload
  metadata/              # per-frame JSON metadata
  stitched/
    realtime_map.jpg     # output of Stitch Realtime
    hq_map.jpg           # output of Stitch HQ
  jetson_images/         # local mirror of the Jetson captures
```

## What was removed (cleanup)

* `jetson/camera.py` — old CSI/V4L2 wrapper, replaced by `rtsp_camera.py`
* `jetson/capture_send.py` — old single-process uploader, replaced by `jetson/run.py`
* `jetson/gps_reader.py` — GPS reader (GPS is currently disabled)
* `pc/viewer.py` — old OpenCV windows (the browser is the viewer now)
* `pc/server.py` — old shim (use `pc/run.py` directly)
* `stitch_now.py` — old one-shot CLI stitcher
* `test.py` — old OpenCV preview window (the dashboard is the preview)

## Endpoints (full reference)

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

## Re-enabling GPS

The capture_send path is removed; if you want GPS back, the easiest
approach is to add a tiny GPS reader to `jetson/run.py` and feed real
coordinates into the metadata dictionary.