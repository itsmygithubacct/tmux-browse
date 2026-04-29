"""HTTP route handlers for spawning/stopping ttyd processes:
``/api/ttyd/start``, ``/api/ttyd/raw``, ``/api/ttyd/stop``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import sessions, ttyd

if TYPE_CHECKING:
    from ..server import Handler


def h_ttyd_start(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    if not sessions.exists(name):
        handler._send_json({"ok": False, "error": f"no such tmux session: {name}"},
                           status=404)
        return
    tls_paths = getattr(handler.server, "tls_paths", None)
    bind_addr = getattr(handler.server, "ttyd_bind_addr", None)
    handler._send_json(ttyd.start(name, tls_paths=tls_paths, bind_addr=bind_addr))


def h_ttyd_raw(handler: "Handler", _parsed: ParseResult, _body: dict) -> None:
    tls_paths = getattr(handler.server, "tls_paths", None)
    bind_addr = getattr(handler.server, "ttyd_bind_addr", None)
    handler._send_json(ttyd.start_raw(tls_paths=tls_paths, bind_addr=bind_addr))


def h_ttyd_stop(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    handler._send_json(ttyd.stop(name))
