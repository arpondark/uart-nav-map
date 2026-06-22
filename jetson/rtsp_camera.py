"""RTSP camera wrapper for IP-based drone cameras (e.g. SIYI / generic ONVIF).

This module replaces the local Pi/CSI cameras for systems where the drone
streams video over RTSP. The wrapper exposes a tiny synchronous API
(:py:meth:`RTSPCamera.read_frame`, :py:meth:`RTSPCamera.capture_jpeg`) so
``run.py`` can stay focused on the upload loop.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

try:
    from jetson import config
except ImportError:  # Allow running from inside jetson/.
    import config  # type: ignore

log = logging.getLogger("rtsp_camera")


def rtsp_pipeline(
    url: str = config.RTSP_URL,
    latency_ms: int = config.RTSP_LATENCY_MS,
    width: int = config.CAMERA_WIDTH,
    height: int = config.CAMERA_HEIGHT,
) -> str:
    """Build a GStreamer pipeline for the RTSP source.

    Falls back to ``cv2.VideoCapture(url)`` if GStreamer is unavailable.
    """

    return (
        f"rtspsrc location={url} latency={latency_ms} ! "
        f"decodebin ! videoconvert ! "
        f"video/x-raw,format=BGR,width={width},height={height} ! "
        f"appsink drop=1 max-buffers=2"
    )


class RTSPCamera:
    """Synchronous RTSP camera wrapper."""

    def __init__(
        self,
        url: str = config.RTSP_URL,
        width: int = config.CAMERA_WIDTH,
        height: int = config.CAMERA_HEIGHT,
        jpeg_quality: int = config.JPEG_QUALITY,
        open_timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality
        self.open_timeout = open_timeout
        self._capture: Optional[cv2.VideoCapture] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def open(self) -> None:
        if self._capture is not None and self._capture.isOpened():
            return

        # Try the GStreamer pipeline first, then fall back to plain RTSP
        # (libav / ffmpeg backend that ships with opencv-python).
        pipeline = rtsp_pipeline(self.url, width=self.width, height=self.height)
        capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not capture.isOpened():
            log.warning("GStreamer pipeline failed for %s; trying plain RTSP.", self.url)
            capture = cv2.VideoCapture(self.url)
            if not capture.isOpened():
                capture.release()
                raise RuntimeError(f"Could not open RTSP stream: {self.url}")
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        deadline = time.monotonic() + self.open_timeout
        ok, _ = capture.read()
        # Drop the first few frames so RTSP handshake / SPS-PPS is complete.
        while not ok and time.monotonic() < deadline:
            time.sleep(0.2)
            ok, _ = capture.read()

        if not ok:
            capture.release()
            raise RuntimeError(
                f"RTSP stream opened but no frames received within {self.open_timeout}s"
            )

        self._capture = capture
        log.info("RTSP stream ready: %s", self.url)

    def close(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None

    # ------------------------------------------------------------------
    # Frame helpers
    # ------------------------------------------------------------------
    def read_frame(self, retries: int = 3) -> Optional[np.ndarray]:
        """Read a single BGR frame, retrying briefly if the decoder is mid-keyframe."""

        if self._capture is None:
            self.open()

        assert self._capture is not None
        for _ in range(max(1, retries)):
            ok, frame = self._capture.read()
            if ok and frame is not None:
                return frame
            time.sleep(0.05)
        return None

    def capture_jpeg(self) -> bytes:
        frame = self.read_frame()
        if frame is None:
            raise RuntimeError("RTSP frame capture failed")
        ok, encoded = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        )
        if not ok:
            raise RuntimeError("JPEG encoding failed")
        return encoded.tobytes()

    def __enter__(self) -> "RTSPCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()