"""HTTP route for the federation peer registry.

Exposes the live peer list at ``GET /api/peers`` so the dashboard
UI's Federation card can show which other hosts are visible. The
session-aggregation pass in :func:`lib.server._session_summary`
also uses :func:`lib.federation.list_peers` directly; this route
is for the UI/diagnostics path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import federation

if TYPE_CHECKING:
    from ..server import Handler


def h_peers(handler: "Handler", _parsed: ParseResult) -> None:
    rows = [{
        "device_id": p.device_id,
        "hostname": p.hostname,
        "dashboard_port": p.dashboard_port,
        "scheme": p.scheme,
        "version": p.version,
        "last_seen": p.last_seen,
        "url": p.base_url,
    } for p in federation.list_peers()]
    handler._send_json({"ok": True, "peers": rows})
