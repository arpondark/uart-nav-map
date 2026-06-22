"""PC-side launcher: opens the web dashboard for the stitcher.

Usage:

    python stitch.py

The PC does **not** capture frames itself. The Jetson (running
``jetson/run.py``) opens the RTSP camera and POSTs each frame to
``/upload`` on this server. As soon as the operator clicks
**Stitch Now** in the dashboard, every new upload is folded into the
live stitched map automatically.

By default the dashboard listens on http://0.0.0.0:5000/. Override with
``DASHBOARD_HOST`` and ``DASHBOARD_PORT``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    try:
        from pc.dashboard_server import main as dashboard_main
    except Exception as exc:
        print(f"Failed to import dashboard server: {exc}")
        return 1
    return dashboard_main()


if __name__ == "__main__":
    raise SystemExit(main())