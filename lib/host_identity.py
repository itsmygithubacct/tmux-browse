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

import socket
import uuid
from pathlib import Path

from . import config


def _device_id_path() -> Path:
    return config.STATE_DIR / "device-id"


def get_or_create_device_id() -> str:
    p = _device_id_path()
    if p.exists():
        existing = p.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    config.ensure_dirs()
    did = str(uuid.uuid4())
    p.write_text(did + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return did


def get_hostname() -> str:
    """Short hostname (first label only) — used in beacons and as the
    ``<host>:<session>`` prefix on remote rows."""
    return socket.gethostname().split(".")[0]
