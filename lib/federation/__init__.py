"""LAN federation — auto-discover peer tmux-browse instances.

Each instance broadcasts a UDP beacon on a fixed port (8095) every
five seconds and listens for the same packets from other peers on
the same broadcast domain. Discovered peers are merged into the
local dashboard's session list, with each remote session's name
prefixed by the originating peer's hostname.

Stdlib-only: ``socket`` for UDP, ``threading`` for the broadcaster
and listener loops. No mDNS, no zeroconf, no pip dependency.

The trust model is "any host on the same LAN can claim to be a
peer." That's appropriate for a single-user / single-tenant LAN
but not for shared networks. Disable with ``--no-federation`` (see
I6).

This module exposes only the registry primitives + the start-up
hook. The HTTP route surface (``/api/peers``) lives in
:mod:`lib.server_routes.peers`; the session aggregation pass lives
in :func:`lib.server._session_summary`.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .. import __version__, config

# Fixed port for both the broadcaster and the listener. UDP: a
# different process on the host can bind the same port at the same
# time, so a second tmux-browse on this machine can still beacon
# (it just won't *receive* — see I2's listener for how that's
# handled). 8095 is one below the dashboard default port (8096) on
# purpose: stays out of the way of HTTP traffic and is easy to
# remember.
BEACON_PORT = 8095

# Beacon cadence and TTL. Five seconds is fine for "did this peer
# just come up?" — phones flipping WiFi see it within ~10s; a
# fresh peer is visible to others within one beacon. The TTL is
# 3× the cadence so a single dropped packet doesn't drop the peer.
BEACON_INTERVAL_SEC = 5
PEER_TTL_SEC = 15


@dataclass
class PeerInfo:
    device_id: str
    hostname: str
    dashboard_port: int
    scheme: str  # "http" | "https"
    version: str
    last_seen: int
    addr: str  # IP address that last sent a beacon

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.addr}:{self.dashboard_port}"


# Persistent device id, generated once per host. Shared across
# tmux-browse processes on the same box so beacons from a
# restarted server look like the same peer to others.
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
    """Short hostname (first label only) for the beacon and for the
    ``<host>:<session>`` prefix on remote rows."""
    return socket.gethostname().split(".")[0]


# Peer registry. The listener thread populates ``_peers``; the
# session-aggregation path reads it. ``_peers_lock`` makes both
# safe under ``ThreadingHTTPServer``'s thread-per-request model.
_peers: dict[str, PeerInfo] = {}
_peers_lock = threading.Lock()


def list_peers(now: int | None = None) -> list[PeerInfo]:
    """Live peers — everything still inside the TTL window."""
    n = now if now is not None else int(time.time())
    with _peers_lock:
        return [p for p in _peers.values() if (n - p.last_seen) < PEER_TTL_SEC]


def gc_peers(now: int | None = None) -> int:
    """Drop peers that haven't beaconed inside the TTL.

    Returns the number of entries dropped — handy for tests."""
    n = now if now is not None else int(time.time())
    with _peers_lock:
        stale = [d for d, p in _peers.items() if (n - p.last_seen) >= PEER_TTL_SEC]
        for d in stale:
            _peers.pop(d, None)
        return len(stale)


def upsert_peer(info: PeerInfo) -> None:
    """Internal — used by the listener thread to record a beacon.

    Public-ish so tests can poke entries in directly."""
    with _peers_lock:
        _peers[info.device_id] = info


def clear_peers() -> None:
    """For tests."""
    with _peers_lock:
        _peers.clear()
