"""Run realtime and HQ stitching once using images already in data/images.

This script does not start the Flask server. It reads existing image files,
writes realtime_map.jpg and hq_map.png into data/stitched, and prints a short
summary so you can see which stitch succeeded.
"""

from __future__ import annotations

import os
import queue
import sys
from time import perf_counter
from pathlib import Path

os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

import cv2

from pc.hq_stitcher import HQStitcher
from pc.realtime_stitcher import RealtimeStitcher
from pc.storage import ensure_directories, list_images


FAST_MODE = os.environ.get("STITCH_FAST", "1").lower() not in {"0", "false", "no"}
FAST_MAX_DIM = int(os.environ.get("STITCH_MAX_DIM", "1200" if FAST_MODE else "2000"))
FAST_WINDOW_SIZES = [4, 6, 8] if FAST_MODE else [8, 10, 12, 15]
FAST_STEP = int(os.environ.get("STITCH_STEP", "1" if FAST_MODE else "2"))


def main() -> int:
    ensure_directories()

    images = list_images()
    print(f"Images found: {len(images)}")
    if not images:
        print("No images found in data/images")
        return 1

    # Report CUDA availability (quick runtime check)
    cuda_count = 0
    try:
        if hasattr(cv2, "cuda"):
            try:
                cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
            except Exception:
                cuda_count = 0
    except Exception:
        cuda_count = 0
    print(f"OpenCV CUDA support: {hasattr(cv2, 'cuda')}, CUDA device count: {cuda_count}")
    print(f"Fast stitching mode: {FAST_MODE}, max dimension: {FAST_MAX_DIM}, window sizes: {FAST_WINDOW_SIZES}, step: {FAST_STEP}")

    realtime_output = Path("data/stitched/realtime_map.jpg")
    hq_output = Path("data/stitched/hq_map.png")

    realtime_queue: "queue.Queue" = queue.Queue()
    realtime = RealtimeStitcher(realtime_queue)
    for image_path in images[-realtime.buffer.maxlen :]:
        realtime.buffer.append(str(image_path))

    print("Running realtime stitch...")
    realtime_started = perf_counter()
    realtime._update_map()
    realtime_elapsed = perf_counter() - realtime_started
    print(f"Realtime stitch time: {realtime_elapsed:.2f}s")
    print(f"Realtime output: {'OK' if realtime_output.exists() else 'MISSING'} -> {realtime_output}")

    print("Running HQ stitch...")
    hq = HQStitcher(queue.Queue())
    hq.image_paths = [str(path) for path in images]
    hq.output_path = hq_output

    hq_started = perf_counter()
    success = False
    for window_size in FAST_WINDOW_SIZES:
        if success:
            break

        for start in range(len(hq.image_paths) - window_size, -1, -FAST_STEP):
            end = start + window_size
            window_paths = hq.image_paths[start:end]
            # Load and downscale large images to limit memory usage
            window_images = []
            skip_window = False
            for path in window_paths:
                img = cv2.imread(path)
                if img is None:
                    skip_window = True
                    break
                h, w = img.shape[:2]
                if max(h, w) > FAST_MAX_DIM:
                    scale = FAST_MAX_DIM / float(max(h, w))
                    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                window_images.append(img)

            if skip_window or not window_images:
                continue

            stitcher = hq._create_hq_stitcher()
            try:
                status, stitched = stitcher.stitch(window_images)
            except cv2.error as e:
                print(f"Stitcher error on window {start}-{end}: {e}")
                continue
            except MemoryError as e:
                print(f"MemoryError while stitching window {start}-{end}: {e}")
                continue

            if status == cv2.Stitcher_OK and stitched is not None:
                hq.output_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(hq.output_path), stitched, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
                print(f"HQ stitched from window {start}-{end}")
                success = True
                break

    hq_elapsed = perf_counter() - hq_started
    print(f"HQ stitch time: {hq_elapsed:.2f}s")
    if not success:
        print("HQ stitch: no successful window found")
    print(f"HQ output: {'OK' if hq_output.exists() else 'MISSING'} -> {hq_output}")

    if realtime_output.exists():
        image = cv2.imread(str(realtime_output))
        if image is not None:
            print(f"Realtime size: {image.shape[1]}x{image.shape[0]}")

    if hq_output.exists():
        image = cv2.imread(str(hq_output))
        if image is not None:
            print(f"HQ size: {image.shape[1]}x{image.shape[0]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())