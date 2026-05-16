# Drone Dual Map System

Automated drone mapping pipeline with two simultaneous map outputs:

- **Realtime map**: fast, low-resolution preview updated on each received frame.
- **HQ map**: higher-quality batch stitch updated every `HQ_BATCH_SIZE` frames or after `HQ_TRIGGER_SECONDS`.

## Structure

```text
drone-mapping/
├── jetson/
│   ├── capture_send.py
│   ├── camera.py
│   ├── gps_reader.py
│   └── config.py
├── pc/
│   ├── server.py
│   ├── storage.py
│   ├── realtime_stitcher.py
│   ├── hq_stitcher.py
│   ├── viewer.py
│   └── config.py
├── data/
│   ├── images/
│   ├── metadata/
│   └── stitched/
│       ├── realtime_map.jpg
│       └── hq_map.jpg
├── requirements.txt
└── README.md
```

## Install

On both PC and Jetson:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run PC Receiver

On the PC:

```bash
python pc/server.py
```

The server listens on:

```text
http://0.0.0.0:5000/upload
```

Useful endpoints:

- `GET /health`
- `GET /maps/realtime`
- `GET /maps/hq`

If the PC has no GUI or OpenCV windows fail, disable the viewer:

```bash
VIEWER_ENABLED=0 python pc/server.py
```

PowerShell:

```powershell
$env:VIEWER_ENABLED="0"; python pc/server.py
```

## Run Jetson Sender

Set the PC IP address, then start capture:

```bash
export PC_UPLOAD_URL="http://<PC_IP>:5000/upload"
python jetson/capture_send.py
```

Optional GPS/camera overrides:

```bash
export GPS_SERIAL_PORT="/dev/ttyUSB0"
export GPS_BAUDRATE="9600"
export CAMERA_INDEX="0"
export CAPTURE_INTERVAL_SECONDS="1.0"
```

## Data Format

Jetson sends:

```text
POST /upload
image: binary JPG
metadata: JSON string
```

Metadata:

```json
{
  "lat": 23.7808875,
  "lon": 90.2792371,
  "time": "2026-05-16T10:15:30.123+00:00",
  "valid": true
}
```

## Outputs

```text
data/images/                 raw JPG frames
data/metadata/               per-frame JSON metadata
data/stitched/realtime_map.jpg
data/stitched/hq_map.jpg
```

## GPU Notes

The HQ worker detects CUDA support with `cv2.cuda.getCudaEnabledDeviceCount()`.
The normal `opencv-python` pip wheel usually does not include CUDA. For RTX 4050 acceleration, install or build an OpenCV package compiled with CUDA support. When CUDA is available, the HQ worker performs GPU upload/grayscale/ORB preparation before the high-quality stitch.

## Flight Conditions

For reliable stitching:

- Maintain 60-80% image overlap.
- Fly slowly and steadily.
- Use a downward-facing camera.
- Avoid fast rotation and heavy motion blur.
- Keep altitude and exposure as stable as possible.

## Important Files

- `jetson/capture_send.py`: continuous capture and HTTP upload loop.
- `jetson/gps_reader.py`: threaded NMEA GPS parser with last-known/fallback coordinates.
- `pc/server.py`: Flask receiver and worker supervisor.
- `pc/realtime_stitcher.py`: fast low-res OpenCV stitcher.
- `pc/hq_stitcher.py`: batch high-quality stitcher with optional CUDA preprocessing.
- `pc/viewer.py`: live OpenCV display windows.
