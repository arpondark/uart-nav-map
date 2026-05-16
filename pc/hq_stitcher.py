"""High-quality batch stitcher with optional CUDA acceleration."""

import queue
import threading
import time
from pathlib import Path

import cv2

try:
    from pc import config
    from pc.storage import StoredFrame, existing_image_strings, paths_that_exist
except ImportError:
    import config  # type: ignore
    from storage import StoredFrame, existing_image_strings, paths_that_exist  # type: ignore


class HQStitcher(threading.Thread):
    def __init__(
        self,
        input_queue: "queue.Queue[StoredFrame]",
        batch_size: int = config.HQ_BATCH_SIZE,
        min_images: int = config.HQ_MIN_IMAGES,
        max_images: int = config.HQ_MAX_IMAGES,
        trigger_seconds: float = config.HQ_TRIGGER_SECONDS,
        output_path: Path = config.HQ_MAP_PATH,
    ) -> None:
        super().__init__(daemon=True)
        self.input_queue = input_queue
        self.batch_size = batch_size
        self.min_images = min_images
        self.max_images = max_images
        self.trigger_seconds = trigger_seconds
        self.output_path = Path(output_path)
        self.image_paths = existing_image_strings(limit=max_images)
        self.new_since_last = 0
        self.last_attempt = 0.0
        self._stop_event = threading.Event()
        self.cuda_available = self._cuda_available()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        print(
            "HQ stitcher started "
            f"(CUDA {'available' if self.cuda_available else 'not available'})."
        )
        while not self._stop_event.is_set():
            self._collect_new_frames()
            now = time.monotonic()
            time_due = now - self.last_attempt >= self.trigger_seconds
            batch_due = self.new_since_last >= self.batch_size

            if len(self.image_paths) >= self.min_images and (batch_due or time_due):
                self.last_attempt = now
                self._stitch_latest_batch()

            time.sleep(0.5)

    def _collect_new_frames(self) -> None:
        while True:
            try:
                frame = self.input_queue.get_nowait()
            except queue.Empty:
                break

            if frame.image_path not in self.image_paths and Path(frame.image_path).exists():
                self.image_paths.append(frame.image_path)
                self.image_paths = paths_that_exist(self.image_paths)[-self.max_images :]
                self.new_since_last += 1

    def _stitch_latest_batch(self) -> None:
        batch_paths = paths_that_exist(self.image_paths)[-self.max_images :]
        images = []
        for path in batch_paths:
            image = cv2.imread(path)
            if image is not None:
                images.append(image)

        if len(images) < self.min_images:
            return

        if self.cuda_available:
            self._run_cuda_feature_pass(images)

        stitcher = self._create_hq_stitcher()
        status, stitched = stitcher.stitch(images)
        if status == cv2.Stitcher_OK and stitched is not None:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(self.output_path), stitched, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            print(f"HQ map updated from {len(images)} frames.")
        else:
            print(f"HQ stitch skipped: OpenCV status {status}")
        self.new_since_last = 0

    def _create_hq_stitcher(self):
        try:
            stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
        except AttributeError:
            stitcher = cv2.Stitcher_create()

        for method_name, value in (
            ("setRegistrationResol", -1),
            ("setSeamEstimationResol", -1),
            ("setCompositingResol", -1),
            ("setPanoConfidenceThresh", 0.35),
            ("setWaveCorrection", True),
        ):
            method = getattr(stitcher, method_name, None)
            if method is not None:
                try:
                    method(value)
                except Exception:
                    pass
        return stitcher

    @staticmethod
    def _cuda_available() -> bool:
        try:
            return hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0
        except Exception:
            return False

    def _run_cuda_feature_pass(self, images: list) -> None:
        """Exercise CUDA upload/grayscale/ORB where OpenCV was built with it.

        Python wheels from pip usually do not include CUDA, but a custom OpenCV
        build on the RTX PC can accelerate this preparation step. OpenCV's
        high-level Stitcher still performs final compositing internally.
        """

        try:
            orb_factory = getattr(cv2, "cuda_ORB", None)
            orb = orb_factory.create(nfeatures=4000) if orb_factory is not None else None
            for image in images:
                gpu_image = cv2.cuda_GpuMat()
                gpu_image.upload(image)
                gpu_gray = cv2.cuda.cvtColor(gpu_image, cv2.COLOR_BGR2GRAY)
                if orb is not None:
                    orb.detectAndComputeAsync(gpu_gray, None)
        except Exception as exc:
            self.cuda_available = False
            print(f"CUDA preprocessing disabled after error: {exc}")
