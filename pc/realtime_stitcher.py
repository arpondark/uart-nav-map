"""Fast low-resolution stitching worker for live map preview."""

import queue
import shutil
import threading
from collections import deque
from pathlib import Path
from typing import Deque, Iterable

import cv2

try:
    from pc import config
    from pc.storage import StoredFrame
except ImportError:
    import config  # type: ignore
    from storage import StoredFrame  # type: ignore


class RealtimeStitcher(threading.Thread):
    def __init__(
        self,
        input_queue: "queue.Queue[StoredFrame]",
        buffer_size: int = config.REALTIME_BUFFER_SIZE,
        resize_width: int = config.REALTIME_RESIZE_WIDTH,
        output_path: Path = config.REALTIME_MAP_PATH,
    ) -> None:
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.buffer: Deque[str] = deque(maxlen=buffer_size)
        self.resize_width = resize_width
        self.output_path = Path(output_path)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        print("Realtime stitcher started.")
        while not self._stop_event.is_set():
            try:
                frame = self.input_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if Path(frame.image_path).exists():
                self.buffer.append(frame.image_path)
                self._update_map()

    def _update_map(self) -> None:
        images = self._load_preview_images(self.buffer)
        if not images:
            return

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        if len(images) == 1:
            cv2.imwrite(str(self.output_path), images[0])
            return

        stitch_mode = getattr(cv2, "Stitcher_SCANS", None)
        try:
            stitcher = cv2.Stitcher_create(stitch_mode) if stitch_mode is not None else cv2.Stitcher_create()
        except AttributeError:
            stitcher = cv2.Stitcher_create()

        status, stitched = stitcher.stitch(images)
        if status == cv2.Stitcher_OK and stitched is not None:
            cv2.imwrite(str(self.output_path), stitched)
            print(f"Realtime map updated from {len(images)} frames.")
            return

        # Keep the preview alive even when overlap is temporarily insufficient.
        latest_path = self.buffer[-1]
        if Path(latest_path).exists():
            shutil.copyfile(latest_path, self.output_path)
        print(f"Realtime stitch skipped: OpenCV status {status}")

    def _load_preview_images(self, paths: Iterable[str]) -> list:
        images = []
        for path in paths:
            image = cv2.imread(path)
            if image is None:
                continue

            height, width = image.shape[:2]
            if width > self.resize_width:
                scale = self.resize_width / float(width)
                image = cv2.resize(image, (self.resize_width, int(height * scale)))

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            images.append(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
        return images
