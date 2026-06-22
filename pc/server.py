"""Backwards-compatible entry point.

The capture/stitch pipeline is now driven by ``pc.dashboard_server`` and
launched from the top-level ``stitch.py`` script. This module keeps the
old import path alive so older deployment scripts (and the README
instructions) continue to work, but it simply delegates to the dashboard
implementation.
"""

from __future__ import annotations


def main() -> int:
    # Late import to keep module-level side effects minimal.
    from pc.dashboard_server import main as dashboard_main

    print(
        "Note: pc/server.py is deprecated. "
        "Use `python stitch.py` to launch the web dashboard."
    )
    return dashboard_main()


if __name__ == "__main__":
    raise SystemExit(main())
