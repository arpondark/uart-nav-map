"""Camera capture helper for Jetson Nano and Raspberry Pi."""

import logging
import sys
import threading
import time
from typing import Optional

import cv2
import numpy as np

try:
    from jetson import config
except ImportError:  # Allows running from inside the jetson/ directory.
    import config  # type: ignore

log = logging.getLogger("camera")

# Stream defaults used by CameraThread.
STREAM_W   = 1280
STREAM_H   = 720
TARGET_FPS = 30

# Optional picamera2 backend (Raspberry Pi / libcamera).
try:
    from picamera2 import Picamera2  # type: ignore
    _PICAMERA2_AVAILABLE = True
except Exception:
    Picamera2 = None  # type: ignore
    _PICAMERA2_AVAILABLE = False


def nvargus_pipeline(
    width: int = STREAM_W,
    height: int = STREAM_H,
    fps: int = TARGET_FPS,
) -> str:
    """GStreamer pipeline for Jetson CSI cameras (nvarguscamerasrc)."""
    return (
        f"nvarguscamerasrc ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"format=NV12, framerate={fps}/1 ! "
        f"nvvidconv ! video/x-raw, width={width}, height={height}, format=BGRx ! "
        f"videoconvert ! video/x-raw, format=BGR ! appsink"
    )


def v4l2_pipeline(
    width: int = STREAM_W,
    height: int = STREAM_H,
    fps: int = TARGET_FPS,
) -> str:
    """GStreamer pipeline for V4L2 USB cameras (and libcamera on RPi via v4l2)."""
    return (
        f"v4l2src device=/dev/video0 ! "
        f"video/x-raw, width={width}, height={height}, framerate={fps}/1 ! "
        f"videoconvert ! video/x-raw, format=BGR ! appsink"
    )


class Camera:
    """Small synchronous wrapper around OpenCV VideoCapture."""

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


# ============================================================
# CAMERA THREAD
# ============================================================
class CameraThread:
    """
    Background frame grabber that works on:
      1) Raspberry Pi CSI camera via picamera2 (libcamera) - preferred on RPi.
      2) /dev/video0 via V4L2/GStreamer - fallback for USB cams and
         libcamera-compat mode on RPi.
      3) nvarguscamerasrc - fallback for Jetson Nano CSI.

    The most recent frame is exposed via read(); it returns a BGR numpy array.
    """

    def __init__(self) -> None:
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self.running = True
        self._cap: Optional[cv2.VideoCapture] = None
        self._picam = None        # picamera2 handle (RPi)
        self._mode = "none"

        # Try picamera2 first (Raspberry Pi CSI camera), then V4L2, then nvargus.
        opened = False
        if self._try_picamera2():
            opened = True
        elif self._try_v4l2():
            opened = True
        elif self._try_nvargus():
            opened = True

        if not opened:
            log.error(
                "Could not open camera. On Raspberry Pi: enable the CSI camera "
                "with `sudo raspi-config` (Interface Options -> Camera) or "
                "`libcamera-hello`, and install `picamera2`. "
                "On Jetson: check the ribbon and `sudo systemctl restart nvargus-daemon`."
            )
            sys.exit(1)

        threading.Thread(target=self._reader, daemon=True).start()
        log.info(f"Camera ready ({self._mode}) {STREAM_W}x{STREAM_H}@{TARGET_FPS}")

    # ------------------------------------------------------------------
    # Backend openers
    # ------------------------------------------------------------------
    def _try_picamera2(self) -> bool:
        """Open the Raspberry Pi CSI camera via libcamera/picamera2."""
        if not _PICAMERA2_AVAILABLE:
            return False
        try:
            picam = Picamera2()
            cfg = picam.create_video_configuration(
                main={"size": (STREAM_W, STREAM_H), "format": "RGB888"},
                controls={"FrameRate": TARGET_FPS},
            )
            picam.configure(cfg)
            picam.start()
            # Warm up auto-exposure / AEC.
            time.sleep(0.5)
            self._picam = picam
            self._mode = "picamera2"
            log.info("picamera2 (libcamera) opened.")
            return True
        except Exception as exc:
            log.warning(f"picamera2 failed: {exc}")
            try:
                if self._picam is not None:
                    self._picam.close()
            except Exception:
                pass
            self._picam = None
            return False

    def _try_v4l2(self) -> bool:
        """Open /dev/video0 (USB cam, or RPi libcamera in legacy v4l2 mode)."""
        pipe = v4l2_pipeline()
        cap = cv2.VideoCapture(pipe, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            self._cap = cap
            self._mode = "v4l2src"
            log.info("v4l2src /dev/video0 opened.")
            return True
        cap.release()

        # Plain V4L2 without GStreamer, in case libcamera-bypass-v4l2 is set up.
        cap2 = cv2.VideoCapture("/dev/video0")
        if cap2.isOpened():
            cap2.set(cv2.CAP_PROP_FRAME_WIDTH, STREAM_W)
            cap2.set(cv2.CAP_PROP_FRAME_HEIGHT, STREAM_H)
            cap2.set(cv2.CAP_PROP_FPS, TARGET_FPS)
            self._cap = cap2
            self._mode = "v4l2src"
            log.info("v4l2src /dev/video0 (no gstreamer) opened.")
            return True
        cap2.release()
        return False

    def _try_nvargus(self) -> bool:
        """Open the Jetson CSI camera via nvarguscamerasrc."""
        pipe = nvargus_pipeline()
        cap = cv2.VideoCapture(pipe, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            self._cap = cap
            self._mode = "nvarguscamerasrc"
            log.info("nvarguscamerasrc opened.")
            return True
        cap.release()
        log.warning("nvarguscamerasrc failed.")
        return False

    # ------------------------------------------------------------------
    # Reader loop
    # ------------------------------------------------------------------
    def _reader(self) -> None:
        while self.running:
            try:
                if self._mode == "picamera2" and self._picam is not None:
                    rgb = self._picam.capture_array()  # HxWx3 RGB
                    if rgb is None:
                        time.sleep(0.001)
                        continue
                    frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                else:
                    assert self._cap is not None
                    ok, frame = self._cap.read()
                    if not ok or frame is None:
                        time.sleep(0.001)
                        continue

                with self._lock:
                    self._frame = frame
            except Exception as exc:
                log.warning(f"reader error: {exc}")
                time.sleep(0.01)

    def read(self) -> Optional[np.ndarray]:
        """Return a copy of the most recent frame (BGR), or None if not ready."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self) -> None:
        self.running = False
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        if self._picam is not None:
            try:
                self._picam.close()
            except Exception:
                pass
            self._picam = None
