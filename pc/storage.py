"""Disk storage for uploaded drone frames and metadata."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

try:
    from pc import config
except ImportError:
    import config  # type: ignore


@dataclass(frozen=True)
class StoredFrame:
    image_path: str
    metadata_path: str
    timestamp: str
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_directories() -> None:
    for directory in (config.IMAGE_DIR, config.METADATA_DIR, config.STITCHED_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def utc_now_string() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def safe_timestamp(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z_.-]+", "_", value)
    return clean.strip("._") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def unique_stem(timestamp: str) -> str:
    base = f"img_{safe_timestamp(timestamp)}"
    stem = base
    counter = 1
    while (config.IMAGE_DIR / f"{stem}.jpg").exists() or (
        config.METADATA_DIR / f"{stem}.json"
    ).exists():
        stem = f"{base}_{counter:03d}"
        counter += 1
    return stem


def save_frame(image_bytes: bytes, metadata: dict) -> StoredFrame:
    ensure_directories()

    timestamp = str(metadata.get("time") or utc_now_string())
    stem = unique_stem(timestamp)
    image_path = config.IMAGE_DIR / f"{stem}.jpg"
    metadata_path = config.METADATA_DIR / f"{stem}.json"

    enriched_metadata = dict(metadata)
    enriched_metadata["received_at"] = utc_now_string()
    enriched_metadata["image_file"] = image_path.name
    enriched_metadata["metadata_file"] = metadata_path.name

    image_path.write_bytes(image_bytes)
    metadata_path.write_text(json.dumps(enriched_metadata, indent=2), encoding="utf-8")

    return StoredFrame(
        image_path=str(image_path),
        metadata_path=str(metadata_path),
        timestamp=timestamp,
        metadata=enriched_metadata,
    )


def list_images(limit: Optional[int] = None) -> List[Path]:
    ensure_directories()
    images = sorted(
        [
            path
            for path in config.IMAGE_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ],
        key=lambda path: path.stat().st_mtime,
    )
    if limit is not None:
        return images[-limit:]
    return images


def existing_image_strings(limit: Optional[int] = None) -> List[str]:
    return [str(path) for path in list_images(limit=limit)]


def paths_that_exist(paths: Iterable[str]) -> List[str]:
    return [path for path in paths if Path(path).exists()]
