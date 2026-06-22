"""Camera capture controller and stitch dispatcher for the dashboard.

This module owns:
  - CaptureController: starts/stops a local camera capture loop, saving JPGs and
    minimal metadata into data/images. No GPS is required for this minimal
    flow.
  - StitchController: holds the realtime stitcher thread. The stitcher is idle
    until ``stitch_now()`` is called; from then on every new frame triggers a
    realtime re-stitch so the live map always includes the newest image.
  - HQController: drives the high-quality batch stitcher. When enabled it
    ingests every new frame into the HQ buffer and triggers a heavy
    re-stitch periodically (every N frames or every T seconds) so the
    high-quality map is always converging on the latest batch.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import cv2

try:
    from pc import config
    from pc.hq_stitcher import HQStitcher
    from pc.realtime_stitcher import RealtimeStitcher
    from pc.storage import (
        StoredFrame,
        ensure_directories,
        existing_image_strings,
        paths_that_exist,
        save_frame,
    )
except ImportError:  # Allow running from inside the pc/ directory.
    import config  # type: ignore
    from hq_stitcher import HQStitcher  # type: ignore
    from realtime_stitcher import RealtimeStitcher  # type: ignore
    from storage import (  # type: ignore
        StoredFrame,
        ensure_directories,
        existing_image_strings,
        paths_that_exist,
        save_frame,
    )


class CaptureController:
    """Capture frames from a local camera and persist them to data/images.

    The class deliberately uses the simple ``Camera`` wrapper from
    ``pc.camera`` so the same capture code runs whether the camera is a USB
    webcam, an OpenCV device, or a remote stream. When the controller is
    stopped it flushes the capture cleanly so frames already on disk stay
    available for stitching.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._status_lock = threading.Lock()
        self._running = False
        self._frame_count = 0
        self._last_image: Optional[str] = None
        self._last_error: Optional[str] = None
        self._started_at: Optional[float] = None
        self._fps = 0.0
        # Bound by ``attach`` to forward frames to the stitch controller.
        self._on_frame = None
        # Bound by ``attach_hq`` to forward frames to the HQ stitcher.
        self._on_hq_frame = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_running(self) -> bool:
        with self._status_lock:
            return self._running

    def status(self) -> dict:
        with self._status_lock:
            return {
                "running": self._running,
                "frame_count": self._frame_count,
                "last_image": self._last_image,
                "last_error": self._last_error,
                "fps": round(self._fps, 2),
                "started_at": self._started_at,
            }

    def record_remote_frame(self, frame: StoredFrame) -> None:
        """Track a frame that arrived via the upload endpoint.

        The Jetson (``jetson/run.py``) is the canonical capture source in the
        PC-only deployment, so the dashboard needs to reflect its frames even
        though no local camera loop is running.
        """

        with self._status_lock:
            self._frame_count += 1
            self._last_image = frame.image_path
            self._last_error = None

    def start(self) -> bool:
        with self._status_lock:
            if self._running:
                return True

        ensure_directories()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            self._thread = None
        with self._status_lock:
            self._running = False

    # ------------------------------------------------------------------
    # Capture loop
    # ------------------------------------------------------------------
    @staticmethod
    def _load_camera_class():
        """Return a ``Camera`` class for local PC capture (development only).

        The PC's local capture path uses a tiny built-in OpenCV wrapper that
        opens ``cv2.VideoCapture(index)`` directly. In production the Jetson
        (``jetson/run.py``) is the canonical capture source.
        """

        class _BuiltinCamera:
            def __init__(self, index: int = 0) -> None:
                self.index = index
                self._capture: Optional[cv2.VideoCapture] = None

            def open(self) -> None:
                self._capture = cv2.VideoCapture(self.index)
                if not self._capture.isOpened():
                    raise RuntimeError(f"Could not open camera index {self.index}")

            def capture_jpeg(self) -> bytes:
                assert self._capture is not None
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    raise RuntimeError("Camera frame capture failed")
                ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if not ok:
                    raise RuntimeError("JPEG encoding failed")
                return encoded.tobytes()

            def close(self) -> None:
                if self._capture is not None:
                    self._capture.release()
                    self._capture = None

        return _BuiltinCamera

    def _run(self) -> None:
        # Lazy import so the dashboard still imports without a camera stack.
        Camera = self._load_camera_class()
        if Camera is None:
            with self._status_lock:
                self._running = False
                self._last_error = "Camera module unavailable."
            return

        camera: Optional[Camera] = None
        try:
            camera = Camera()
            camera.open()
        except Exception as exc:
            with self._status_lock:
                self._running = False
                self._last_error = f"Camera open failed: {exc}"
            return

        with self._status_lock:
            self._running = True
            self._started_at = time.time()
            self._frame_count = 0
            self._last_error = None

        interval = max(0.0, float(getattr(config, "CAPTURE_INTERVAL_SECONDS", 1.0)))
        last_window = time.monotonic()
        window_count = 0

        while not self._stop_event.is_set():
            loop_started = time.monotonic()
            try:
                image_bytes = camera.capture_jpeg()
                metadata = {
                    "lat": 0.0,
                    "lon": 0.0,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "valid": False,
                }
                frame = save_frame(image_bytes, metadata)
                with self._status_lock:
                    self._frame_count += 1
                    self._last_image = frame.image_path
                window_count += 1

                # Notify listeners (the stitch controller).
                if self._on_frame is not None:
                    try:
                        self._on_frame(frame)
                    except Exception as exc:  # pragma: no cover - listener errors.
                        with self._status_lock:
                            self._last_error = f"Frame listener error: {exc}"

                if self._on_hq_frame is not None:
                    try:
                        self._on_hq_frame(frame)
                    except Exception as exc:
                        with self._status_lock:
                            self._last_error = f"HQ listener error: {exc}"
            except Exception as exc:
                with self._status_lock:
                    self._last_error = f"Capture error: {exc}"

            now = time.monotonic()
            if now - last_window >= 1.0:
                with self._status_lock:
                    self._fps = window_count / (now - last_window)
                last_window = now
                window_count = 0

            elapsed = time.monotonic() - loop_started
            sleep_for = max(0.0, interval - elapsed)
            if self._stop_event.wait(sleep_for):
                break

        with self._status_lock:
            self._running = False
        if camera is not None:
            try:
                camera.close()
            except Exception:
                pass


class StitchController:
    """Owns the realtime stitcher and decides when stitching runs.

    Until ``stitch_now`` is invoked the stitcher is dormant: it keeps an empty
    buffer. Once enabled, every delivered frame is appended to the stitch
    buffer and triggers an immediate re-stitch so the live map always shows
    the most recent content.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._last_status = "idle"
        self._last_stitch_ms: Optional[float] = None
        self._last_stitch_at: Optional[float] = None
        self._frame_count = 0
        self._listener_lock = threading.Lock()
        self._on_capture_start = None
        self._on_capture_stop = None

        # We drive the stitcher manually: the worker thread would race with
        # ``_trigger_stitch`` and re-render the map on every queue event, but
        # we want one explicit re-stitch per delivered frame so the buffer
        # state and the output stay in lock-step.
        self._stitcher = RealtimeStitcher(
            input_queue=None,  # type: ignore[arg-type]
            buffer_size=config.REALTIME_BUFFER_SIZE,
            resize_width=config.REALTIME_RESIZE_WIDTH,
            output_path=config.REALTIME_MAP_PATH,
        )

    # ------------------------------------------------------------------
    # Lifecycle / state queries
    # ------------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            return {
                "stitching": self._enabled,
                "last_status": self._last_status,
                "last_stitch_ms": self._last_stitch_ms,
                "last_stitch_at": self._last_stitch_at,
                "buffer_size": len(self._stitcher.buffer),
                "frames_consumed": self._frame_count,
                "realtime_map_exists": config.REALTIME_MAP_PATH.exists(),
            }

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def stop(self) -> None:
        # The stitcher worker thread is intentionally not started (we drive
        # it from the controller's own ``on_frame`` callback) so there's no
        # join target here. We still call ``stop`` so the thread's stop
        # event is set in case it ever does start.
        try:
            self._stitcher.stop()
            if self._stitcher.is_alive():
                self._stitcher.join(timeout=2.0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Stitch control
    # ------------------------------------------------------------------
    def stitch_now(self) -> dict:
        """Enable real-time stitching and trigger an immediate stitch.

        Until stopped, every subsequent frame is appended and re-stitched
        automatically.
        """

        with self._lock:
            self._enabled = True
            self._last_status = "starting"

        # Reset the rolling buffer and seed it with the most recent on-disk
        # images so the first live map has more than one frame to work with.
        self._stitcher.buffer.clear()
        self._seed_from_disk()

        result = self._trigger_stitch()
        with self._lock:
            self._last_status = "running" if self._stitcher.output_path.exists() else "empty"
        return result

    def stitch_stop(self) -> dict:
        with self._lock:
            self._enabled = False
            self._last_status = "stopped"
        return {"ok": True, "stitching": False}

    # ------------------------------------------------------------------
    # Frame ingest (called by CaptureController)
    # ------------------------------------------------------------------
    def on_frame(self, frame: StoredFrame) -> None:
        """Forward a captured frame to the stitcher and re-stitch live."""

        with self._lock:
            self._frame_count += 1

        if not self.is_enabled():
            return

        # Append to the stitcher's rolling buffer so the live map covers the
        # most recent frames.
        self._stitcher.buffer.append(frame.image_path)
        self._trigger_stitch()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _seed_from_disk(self, limit: Optional[int] = None) -> None:
        """Backfill the stitcher buffer with recent on-disk images."""

        try:
            from pc.storage import list_images  # type: ignore
        except Exception:
            from storage import list_images  # type: ignore

        seed = list_images(limit=limit or config.REALTIME_BUFFER_SIZE * 2)
        for path in seed:
            self._stitcher.buffer.append(str(path))

    def _trigger_stitch(self) -> dict:
        started = time.monotonic()
        try:
            self._stitcher._update_map()
            ok = self._stitcher.output_path.exists()
            elapsed_ms = (time.monotonic() - started) * 1000.0
            with self._lock:
                self._last_stitch_ms = elapsed_ms
                self._last_stitch_at = time.time()
            return {
                "ok": ok,
                "buffer": len(self._stitcher.buffer),
                "elapsed_ms": round(elapsed_ms, 1),
                "output": str(self._stitcher.output_path),
            }
        except Exception as exc:
            with self._lock:
                self._last_status = f"error: {exc}"
            return {"ok": False, "error": str(exc)}


def attach(capture: CaptureController, stitch: StitchController) -> None:
    """Wire the capture controller to forward frames to the stitcher."""

    capture._on_frame = stitch.on_frame


def attach_hq(capture: CaptureController, hq: "HQController") -> None:
    """Wire the capture controller to forward frames to the HQ stitcher."""

    capture._on_hq_frame = hq.on_frame


class HQController:
    """High-quality batch stitcher driver.

    Until ``start()`` is called, the HQ worker is dormant. Once enabled it
    ingests every new frame into its image batch and periodically runs a
    full OpenCV stitcher over the latest window. The heavy work is
    offloaded to a background thread so the HTTP request that triggered
    the start returns immediately.
    """

    def __init__(
        self,
        batch_size: int = config.HQ_BATCH_SIZE,
        min_images: int = config.HQ_MIN_IMAGES,
        max_images: int = config.HQ_MAX_IMAGES,
        trigger_seconds: float = config.HQ_TRIGGER_SECONDS,
        output_path: Path = config.HQ_MAP_PATH,
    ) -> None:
        self._lock = threading.Lock()
        self._enabled = False
        self._batch_size = batch_size
        self._min_images = min_images
        self._max_images = max_images
        self._trigger_seconds = trigger_seconds
        self.output_path = Path(output_path)
        self._image_paths: list[str] = existing_image_strings(limit=max_images)
        self._new_since_last = 0
        self._last_attempt = 0.0
        self._last_status = "idle"
        self._last_stitch_ms: Optional[float] = None
        self._last_stitch_at: Optional[float] = None
        self._last_image_count = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stitch_lock = threading.Lock()  # serialises _stitch_latest_batch
        self._cuda_available = self._check_cuda()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled,
                "last_status": self._last_status,
                "last_stitch_ms": self._last_stitch_ms,
                "last_stitch_at": self._last_stitch_at,
                "buffer_size": len(self._image_paths),
                "new_since_last": self._new_since_last,
                "last_image_count": self._last_image_count,
                "hq_map_exists": self.output_path.exists(),
                "cuda_available": self._cuda_available,
                "batch_size": self._batch_size,
                "trigger_seconds": self._trigger_seconds,
            }

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> dict:
        """Enable the HQ stitcher and trigger an initial run if possible."""

        with self._lock:
            if self._enabled:
                return {"ok": True, "already_running": True, **self.status()}
            self._enabled = True
            self._last_status = "starting"
            self._new_since_last = 0
            self._last_attempt = time.monotonic()

        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

        # Run the first stitch in the background; return immediately.
        threading.Thread(target=self._stitch_latest_batch, daemon=True).start()
        return {"ok": True, **self.status()}

    def stop(self) -> dict:
        with self._lock:
            self._enabled = False
            self._last_status = "stopped"
        return {"ok": True, **self.status()}

    def shutdown(self) -> None:
        with self._lock:
            self._enabled = False
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Frame ingest
    # ------------------------------------------------------------------
    def on_frame(self, frame: StoredFrame) -> None:
        with self._lock:
            if frame.image_path not in self._image_paths and Path(frame.image_path).exists():
                self._image_paths.append(frame.image_path)
                self._image_paths = paths_that_exist(self._image_paths)[-self._max_images :]
                self._new_since_last += 1

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            time_due = now - self._last_attempt >= self._trigger_seconds
            batch_due = False
            with self._lock:
                batch_due = self._new_since_last >= self._batch_size
                count = len(self._image_paths)
                if self._enabled and count >= self._min_images and (batch_due or time_due):
                    self._last_attempt = now
                    self._new_since_last = 0
                    should_stitch = True
                else:
                    should_stitch = False

            if should_stitch:
                self._stitch_latest_batch()
            self._stop_event.wait(0.5)

    def _stitch_latest_batch(self) -> None:
        with self._stitch_lock:
            started = time.monotonic()
            with self._lock:
                batch_paths = paths_that_exist(self._image_paths)[-self._max_images :]

            if len(batch_paths) < self._min_images:
                with self._lock:
                    self._last_status = "empty"
                return

            images = []
            for path in batch_paths:
                image = cv2.imread(path)
                if image is not None:
                    images.append(image)

            if len(images) < self._min_images:
                with self._lock:
                    self._last_status = "empty"
                return

            stitcher = self._create_stitcher()
            try:
                status, stitched = stitcher.stitch(images)
            except cv2.error as exc:
                with self._lock:
                    self._last_status = f"error: {exc}"
                return

            elapsed_ms = (time.monotonic() - started) * 1000.0
            with self._lock:
                self._last_stitch_ms = elapsed_ms
                self._last_stitch_at = time.time()
                self._last_image_count = len(images)

            if status == cv2.Stitcher_OK and stitched is not None:
                self.output_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(
                    str(self.output_path), stitched, [int(cv2.IMWRITE_JPEG_QUALITY), 95]
                )
                with self._lock:
                    self._last_status = "running"
            else:
                with self._lock:
                    self._last_status = f"skipped ({status})"

    def _create_stitcher(self):
        stitch_mode = getattr(cv2, "Stitcher_SCANS", None)
        try:
            stitcher = cv2.Stitcher_create(stitch_mode) if stitch_mode is not None else cv2.Stitcher_create()
        except AttributeError:
            stitcher = cv2.Stitcher_create()

        for method_name, value in (
            ("setRegistrationResol", -1),
            ("setSeamEstimationResol", -1),
            ("setCompositingResol", -1),
            ("setPanoConfidenceThresh", 0.35),
            ("setWaveCorrection", False),
        ):
            method = getattr(stitcher, method_name, None)
            if method is not None:
                try:
                    method(value)
                except Exception:
                    pass
        return stitcher

    @staticmethod
    def _check_cuda() -> bool:
        try:
            return hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            return False