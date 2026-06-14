"""Host identity primitives — stable device_id and short hostname.

These two values describe the *host* tmux-browse runs on, not the
federation feature. The dashboard tags every session row with them so
local and federated rows render symmetrically (the local hostname
badge is the same shape as a peer's). Federation reads them from
here too; if the federation extension is not installed, the device_id
field on session rows still renders.

The device_id is a UUID generated on first read and persisted to
``~/.tmux-browse/device-id`` (mode 0600). It survives restarts so a
peer that has paired with us still recognizes us after a reboot.
"""

from __future__ import annotations

import os
import socket
import threading
import uuid
from pathlib import Path

from . import config

# The device_id is stable for the process lifetime, but the dashboard's
# hot path (``_session_summary``) reads it on every request. Cache it so
# that's a single in-memory read instead of a per-request disk stat+read.
_cache_lock = threading.Lock()
_cached_device_id: str | None = None


def _device_id_path() -> Path:
    return config.STATE_DIR / "device-id"


def _read_device_id(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _load_or_create_device_id() -> str:
    p = _device_id_path()
    existing = _read_device_id(p)
    if existing:
        return existing
    config.ensure_dirs()
    candidate = str(uuid.uuid4())
    # Exclusive create with 0600 from the start: no world-readable window
    # (the old write-then-chmod left one), and race-safe — if another
    # process created the file between our read and open, we adopt theirs
    # rather than clobbering it, so all callers converge on one id.
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_device_id(p) or candidate
    except OSError:
        # Can't create the file (e.g. read-only FS) — still return a
        # usable id for this process rather than raising into a request.
        return candidate
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(candidate + "\n")
    return candidate


def get_or_create_device_id() -> str:
    global _cached_device_id
    if _cached_device_id is not None:
        return _cached_device_id
    with _cache_lock:
        if _cached_device_id is None:
            _cached_device_id = _load_or_create_device_id()
        return _cached_device_id


def get_hostname() -> str:
    """Short hostname (first label only) — used in beacons and as the
    ``<host>:<session>`` prefix on remote rows."""
    return socket.gethostname().split(".")[0]
