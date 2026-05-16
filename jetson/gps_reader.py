"""Threaded NMEA GPS reader."""

import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import pynmea2

try:
    import serial
except ImportError:  # pyserial is listed in requirements.txt.
    serial = None  # type: ignore

try:
    from jetson import config
except ImportError:
    import config  # type: ignore


@dataclass
class GPSFix:
    lat: float
    lon: float
    time: str
    valid: bool = False

    def to_metadata(self) -> dict:
        return asdict(self)


class GPSReader(threading.Thread):
    """Continuously reads GPS and keeps the latest valid fix available."""

    def __init__(
        self,
        port: str = config.GPS_SERIAL_PORT,
        baudrate: int = config.GPS_BAUDRATE,
        timeout: float = config.GPS_TIMEOUT_SECONDS,
        fallback_lat: float = config.FALLBACK_LAT,
        fallback_lon: float = config.FALLBACK_LON,
    ) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest = GPSFix(
            lat=fallback_lat,
            lon=fallback_lon,
            time=self._utc_now(),
            valid=False,
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def run(self) -> None:
        if serial is None:
            print("pyserial is not installed; GPSReader will use fallback coordinates.")
            return

        while not self._stop_event.is_set():
            try:
                with serial.Serial(self.port, self.baudrate, timeout=self.timeout) as gps:
                    print(f"GPS connected on {self.port} at {self.baudrate} baud")
                    self._read_loop(gps)
            except Exception as exc:
                print(f"GPS connection/read error: {exc}. Retrying in 2 seconds.")
                time.sleep(2.0)

    def _read_loop(self, gps) -> None:
        while not self._stop_event.is_set():
            raw_line = gps.readline()
            if not raw_line:
                continue

            try:
                line = raw_line.decode("ascii", errors="ignore").strip()
                if not line.startswith("$"):
                    continue
                message = pynmea2.parse(line)
                fix = self._message_to_fix(message)
                if fix is not None:
                    with self._lock:
                        self._latest = fix
            except pynmea2.ParseError:
                continue
            except Exception as exc:
                print(f"GPS parse error: {exc}")

    def _message_to_fix(self, message) -> Optional[GPSFix]:
        lat = getattr(message, "latitude", None)
        lon = getattr(message, "longitude", None)
        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return None

        if lat == 0.0 and lon == 0.0:
            return None

        gps_time = self._utc_now()
        datestamp = getattr(message, "datestamp", None)
        timestamp = getattr(message, "timestamp", None)
        if datestamp is not None and timestamp is not None:
            gps_time = datetime.combine(datestamp, timestamp, tzinfo=timezone.utc).isoformat(
                timespec="milliseconds"
            )

        return GPSFix(lat=lat, lon=lon, time=gps_time, valid=True)

    def get_fix(self) -> GPSFix:
        with self._lock:
            latest = GPSFix(**self._latest.to_metadata())

        if not latest.valid:
            latest.time = self._utc_now()
        return latest

    def stop(self) -> None:
        self._stop_event.set()
