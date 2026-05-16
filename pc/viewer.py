"""OpenCV viewer for latest frame, realtime map, and HQ map."""

import queue
import threading
import time
from pathlib import Path
from typing import Optional

import cv2

try:
    from pc import config
    from pc.storage import StoredFrame
except ImportError:
    import config  # type: ignore
    from storage import StoredFrame  # type: ignore


class MapViewer(threading.Thread):
    def __init__(
        self,
        latest_queue: "queue.Queue[StoredFrame]",
        realtime_map_path: Path = config.REALTIME_MAP_PATH,
        hq_map_path: Path = config.HQ_MAP_PATH,
        refresh_ms: int = config.VIEWER_REFRESH_MS,
    ) -> None:
        super().__init__(daemon=True)
        self.latest_queue = latest_queue
        self.realtime_map_path = Path(realtime_map_path)
        self.hq_map_path = Path(hq_map_path)
        self.refresh_ms = refresh_ms
        self.latest_image_path: Optional[str] = None
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        print("Viewer started.")
        try:
            self._run_windows()
        except cv2.error as exc:
            print(f"Viewer disabled: OpenCV window error: {exc}")

    def _run_windows(self) -> None:
        while not self._stop_event.is_set():
            self._drain_latest_queue()
            self._show_image("LIVE FEED", self.latest_image_path)
            self._show_image("REALTIME MAP", str(self.realtime_map_path))
            self._show_image("HQ MAP", str(self.hq_map_path))

            key = cv2.waitKey(self.refresh_ms) & 0xFF
            if key == ord("q"):
                self.stop()

            time.sleep(0.01)

        cv2.destroyAllWindows()

    def _drain_latest_queue(self) -> None:
        while True:
            try:
                frame = self.latest_queue.get_nowait()
            except queue.Empty:
                break
            self.latest_image_path = frame.image_path

    def _show_image(self, title: str, path: Optional[str]) -> None:
        if not path or not Path(path).exists():
            return

        image = cv2.imread(path)
        if image is None:
            return

        height, width = image.shape[:2]
        max_width = 900
        if width > max_width:
            scale = max_width / float(width)
            image = cv2.resize(image, (max_width, int(height * scale)))

        cv2.imshow(title, image)
