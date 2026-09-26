"""Phase 2 - store and manage audio files.

Every recording (WAV) and every spoken reply is saved with a timestamped name,
and only the newest ``KEEP_LAST_FILES`` files per folder are kept. Recordings can
be copied into ``backend/evaluation/samples`` to reuse them for testing.
Saving never breaks a request: problems are logged and ignored.
"""
import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)


def _save(kind: str, prefix: str, data: bytes, suffix: str) -> Path | None:
    if not settings.STORE_AUDIO:
        return None
    try:
        directory = Path(settings.AUDIO_DIR) / kind
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = directory / f"{prefix}_{stamp}{suffix}"
        path.write_bytes(data)
        cleanup(directory)
        return path
    except OSError as exc:
        log.warning("Could not store %s audio: %s", kind, exc)
        return None


def save_recording(data: bytes, suffix: str = ".wav") -> Path | None:
    return _save("recordings", "input", data, suffix)


def save_response(data: bytes, suffix: str = ".wav") -> Path | None:
    return _save("responses", "reply", data, suffix)


def cleanup(directory: Path, keep: int | None = None) -> None:
    """Delete all but the newest ``keep`` files in ``directory``."""
    keep = settings.KEEP_LAST_FILES if keep is None else keep
    files = sorted(
        (p for p in Path(directory).glob("*") if p.is_file() and p.name != ".gitkeep"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
