"""Camera capture helper for the Jetson Nano."""

import time
from typing import Optional

import cv2

try:
    from jetson import config
except ImportError:  # Allows running from inside the jetson/ directory.
    import config  # type: ignore


class Camera:
    """Small wrapper around OpenCV VideoCapture."""

    def __init__(
        self,
        index: int = config.CAMERA_INDEX,
        width: int = config.CAMERA_WIDTH,
        height: int = config.CAMERA_HEIGHT,
        fps: int = config.CAMERA_FPS,
        jpeg_quality: int = config.JPEG_QUALITY,
    ) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._capture: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        self._capture = cv2.VideoCapture(self.index)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open camera index {self.index}")

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._capture.set(cv2.CAP_PROP_FPS, self.fps)

        # Let auto exposure and frame buffers settle before the first capture.
        time.sleep(0.5)

    def capture_jpeg(self) -> bytes:
        if self._capture is None:
            self.open()

        assert self._capture is not None
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError("Camera frame capture failed")

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        ok, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            raise RuntimeError("JPEG encoding failed")

        return encoded.tobytes()

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
