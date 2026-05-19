"""Standalone OpenCV preview for realtime and HQ stitched maps.

Run from the repository root while the stitching workers are writing files.
The window opens on the realtime preview, refreshes it as the file changes,
and enables an HQ button once the high-quality map exists.
"""

from __future__ import annotations

import time
from time import perf_counter
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Quick CUDA device count for display
CUDA_COUNT = 0
try:
    if hasattr(cv2, "cuda"):
        try:
            CUDA_COUNT = cv2.cuda.getCudaEnabledDeviceCount()
        except Exception:
            CUDA_COUNT = 0
except Exception:
    CUDA_COUNT = 0


PROJECT_ROOT = Path(__file__).resolve().parent
STITCHED_DIR = PROJECT_ROOT / "data" / "stitched"
REALTIME_CANDIDATES = [
    STITCHED_DIR / "realtime_map.jpg",
    STITCHED_DIR / "test_realtime_low.jpg",
]
HQ_CANDIDATES = [
    STITCHED_DIR / "hq_map.png",
    STITCHED_DIR / "test_hq_high.jpg",
]

WINDOW_NAME = "UART Nav Map Preview"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 900
TOP_BAR_HEIGHT = 92
PADDING = 20

BTN_REALTIME = (24, 24, 180, 66)
BTN_HQ = (212, 24, 388, 66)


def pick_existing_path(candidates: list[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def stretch_image(image: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
    target_width = max(1, target_width)
    target_height = max(1, target_height)
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)


def draw_text(canvas: np.ndarray, text: str, origin: tuple[int, int], color=(240, 240, 240), scale=0.55, thickness=1) -> None:
    cv2.putText(
        canvas,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_button(canvas: np.ndarray, rect: tuple[int, int, int, int], label: str, active: bool, enabled: bool) -> None:
    x1, y1, x2, y2 = rect
    if not enabled:
        fill = (70, 70, 70)
        border = (110, 110, 110)
        text_color = (170, 170, 170)
    elif active:
        fill = (40, 130, 90)
        border = (90, 210, 160)
        text_color = (255, 255, 255)
    else:
        fill = (45, 45, 45)
        border = (120, 120, 120)
        text_color = (245, 245, 245)

    cv2.rectangle(canvas, (x1, y1), (x2, y2), fill, thickness=-1)
    cv2.rectangle(canvas, (x1, y1), (x2, y2), border, thickness=2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 1
    (text_width, text_height), _ = cv2.getTextSize(label, font, scale, thickness)
    text_x = x1 + (x2 - x1 - text_width) // 2
    text_y = y1 + (y2 - y1 + text_height) // 2
    cv2.putText(canvas, label, (text_x, text_y), font, scale, text_color, thickness, cv2.LINE_AA)


def inside(rect: tuple[int, int, int, int], x: int, y: int) -> bool:
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def build_canvas(preview: Optional[np.ndarray], selected: str, realtime_ready: bool, hq_ready: bool, status: str) -> np.ndarray:
    canvas = np.full((WINDOW_HEIGHT, WINDOW_WIDTH, 3), (18, 18, 22), dtype=np.uint8)
    draw_button(canvas, BTN_REALTIME, "Realtime", active=selected == "realtime", enabled=True)
    draw_button(canvas, BTN_HQ, "HQ Preview", active=selected == "hq", enabled=hq_ready)

    status_x = BTN_HQ[2] + 18
    draw_text(canvas, f"Mode: {selected.upper()}", (status_x, 49), scale=0.65)
    draw_text(canvas, f"CUDA devices: {CUDA_COUNT}", (status_x + 260, 49), scale=0.55)
    draw_text(canvas, f"Realtime: {'ready' if realtime_ready else 'missing'}", (status_x, 76), color=(190, 220, 255), scale=0.5)
    draw_text(
        canvas,
        f"HQ: {'ready - click HQ Preview' if hq_ready else 'waiting for file'}",
        (status_x + 240, 76),
        color=(200, 255, 200) if hq_ready else (210, 210, 210),
        scale=0.5,
    )

    content_top = TOP_BAR_HEIGHT
    content_left = PADDING
    content_right = WINDOW_WIDTH - PADDING
    content_bottom = WINDOW_HEIGHT - PADDING
    content_width = content_right - content_left
    content_height = content_bottom - content_top

    if preview is None:
        draw_text(canvas, status, (PADDING, content_top + 64), color=(240, 240, 240), scale=0.8, thickness=2)
        draw_text(canvas, f"Realtime path: {REALTIME_CANDIDATES[0]}", (PADDING, content_top + 110), color=(200, 200, 200), scale=0.52)
        draw_text(canvas, f"HQ path: {HQ_CANDIDATES[0]}", (PADDING, content_top + 140), color=(200, 200, 200), scale=0.52)
        return canvas

    preview = stretch_image(preview, content_width, content_height)
    preview_area = canvas[content_top : content_top + content_height, content_left : content_left + content_width]
    preview_area[:] = preview

    if status:
        draw_text(canvas, status, (PADDING, WINDOW_HEIGHT - 10), color=(210, 210, 210), scale=0.45)
    return canvas


def main() -> int:
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WINDOW_WIDTH, WINDOW_HEIGHT)

    state = {
        "selected": "realtime",
        "frame": None,
        "last_path": None,
        "last_mtime": 0.0,
        "last_refresh_ms": None,
        "realtime_path": None,
        "hq_path": None,
        "realtime_ready": False,
        "hq_ready": False,
        "status": "Waiting for stitched map files...",
    }

    def refresh_frame() -> None:
        realtime_path = pick_existing_path(REALTIME_CANDIDATES)
        hq_path = pick_existing_path(HQ_CANDIDATES)
        state["realtime_path"] = realtime_path
        state["hq_path"] = hq_path
        state["realtime_ready"] = realtime_path is not None
        state["hq_ready"] = hq_path is not None

        selected_path = realtime_path if state["selected"] == "realtime" else hq_path
        if selected_path is None:
            selected_path = realtime_path or hq_path
            if selected_path is None:
                state["frame"] = build_canvas(None, state["selected"], state["realtime_ready"], state["hq_ready"], state["status"])
                return
            state["selected"] = "realtime" if selected_path == realtime_path else "hq"

        mtime = selected_path.stat().st_mtime
        if state["last_path"] == selected_path and mtime == state["last_mtime"] and state["frame"] is not None:
            return

        refresh_started = perf_counter()
        image = cv2.imread(str(selected_path))
        if image is None:
            state["frame"] = build_canvas(None, state["selected"], state["realtime_ready"], state["hq_ready"], f"Cannot read: {selected_path}")
            return

        state["frame"] = build_canvas(
            image,
            state["selected"],
            state["realtime_ready"],
            state["hq_ready"],
            f"Showing: {selected_path.name}",
        )
        state["last_path"] = selected_path
        state["last_mtime"] = mtime
        state["last_refresh_ms"] = (perf_counter() - refresh_started) * 1000.0

        if state["selected"] == "realtime" and state["last_refresh_ms"] is not None:
            draw_text(
                state["frame"],
                f"Realtime refresh: {state['last_refresh_ms']:.0f} ms",
                (PADDING, WINDOW_HEIGHT - 38),
                color=(120, 255, 180),
                scale=0.55,
                thickness=2,
            )

    def on_mouse(event, x, y, flags, userdata) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if inside(BTN_REALTIME, x, y):
            state["selected"] = "realtime"
            state["last_path"] = None
            return
        if inside(BTN_HQ, x, y) and state["hq_ready"]:
            state["selected"] = "hq"
            state["last_path"] = None

    cv2.setMouseCallback(WINDOW_NAME, on_mouse)

    while True:
        refresh_frame()
        cv2.imshow(WINDOW_NAME, state["frame"])

        key = cv2.waitKey(100) & 0xFF
        if key in (27, ord("q")):
            break

        time.sleep(0.02)

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())