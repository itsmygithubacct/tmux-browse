"""HTTP route handlers for non-feature-specific endpoints:
the dashboard HTML, favicon, ``/health``, and ``/api/server/restart``.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import static, templates

if TYPE_CHECKING:
    from ..server import Handler


def h_index(handler: "Handler", _parsed: ParseResult) -> None:
    reg = handler.server.extension_registry
    handler._send_html(templates.render_index(
        ui_blocks=reg.ui_blocks,
        extension_js=reg.static_js,
    ))


def h_favicon(handler: "Handler", _parsed: ParseResult) -> None:
    body = static.FAVICON_SVG.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "image/svg+xml")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(body)


def h_health(handler: "Handler", _parsed: ParseResult) -> None:
    handler._send_json({"ok": True})


def h_server_restart(handler: "Handler", _parsed: ParseResult, _body: dict) -> None:
    # Lazy import — avoids a circular import on module load. ``_restart_self``
    # uses module-level ``_dashboard_state_*`` machinery in ``lib.server``.
    from ..server import _restart_self
    handler._send_json({"ok": True, "restarting": True})
    threading.Thread(target=_restart_self, daemon=True).start()
