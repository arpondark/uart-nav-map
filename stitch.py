"""PC-side launcher (top-level alias for ``pc/run.py``).

The single script to run on the PC is ``pc/run.py``. This file is kept
as a convenience so existing commands (``python stitch.py``) continue
to work; it just delegates to ``pc/run.py``.
"""

from pc.run import main


if __name__ == "__main__":
    raise SystemExit(main())