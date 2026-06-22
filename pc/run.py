"""PC entry point: starts the web dashboard with capture + all stitch modes.

Run this on the PC that the operator wants to use as the map receiver:

    python pc/run.py

It launches:

* A Flask web dashboard on ``http://0.0.0.0:5000`` (override with
  ``DASHBOARD_HOST`` / ``DASHBOARD_PORT``).
* A ``/upload`` endpoint that accepts frames from the Jetson
  (``jetson/run.py``).
* A realtime stitcher (low resolution, fast, every-frame update).
* A high-quality batch stitcher (heavier, runs every
  ``HQ_BATCH_SIZE`` frames or every ``HQ_TRIGGER_SECONDS``).

The operator controls everything from the web UI: Start/Stop Capture,
Stitch Realtime, Stitch HQ, Stitch All, and Stop. There is no other
script to run on the PC.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from pc.dashboard_server import main as dashboard_main
    return dashboard_main()


if __name__ == "__main__":
    raise SystemExit(main())