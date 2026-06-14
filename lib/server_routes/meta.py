"""HTTP route handlers for non-feature-specific endpoints:
the dashboard HTML, favicon, ``/health``, and ``/api/server/restart``.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import config, static, templates

if TYPE_CHECKING:
    from ..server import Handler


_STATIC_DIR = config.PROJECT_DIR / "static"


def _send_static_file(handler: "Handler", name: str, content_type: str,
                      cache_control: str,
                      extra_headers: dict[str, str] | None = None) -> None:
    """Serve a file from the static dir, or a clean 404 if it's missing.

    Reading the bytes inline previously let a missing asset (partial
    install, misconfigured PROJECT_DIR) bubble up as an opaque 500. A 404
    naming the asset is far more actionable — especially for the PWA
    manifest / service worker, where a 500 reads as a server fault.
    """
    try:
        body = (_STATIC_DIR / name).read_bytes()
    except OSError:
        handler._send_json(
            {"ok": False, "error": f"missing static asset: {name}"},
            status=404)
        return
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache_control)
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler._safe_write(body)


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
    handler._safe_write(body)


def h_health(handler: "Handler", _parsed: ParseResult) -> None:
    handler._send_json({"ok": True})


def h_server_restart(handler: "Handler", _parsed: ParseResult, _body: dict) -> None:
    if not handler._check_unlock():
        return
    # Lazy import — avoids a circular import on module load. ``_restart_self``
    # uses module-level ``_dashboard_state_*`` machinery in ``lib.server``.
    from ..server import _restart_self
    handler._send_json({"ok": True, "restarting": True})
    threading.Thread(target=_restart_self, daemon=True).start()


def h_manifest(handler: "Handler", _parsed: ParseResult) -> None:
    _send_static_file(handler, "manifest.webmanifest",
                      "application/manifest+json", "public, max-age=86400")


def h_service_worker(handler: "Handler", _parsed: ParseResult) -> None:
    # Service workers MUST be served with no-cache so updates are
    # picked up on next page load — otherwise stale SWs persist for
    # 24h+ and operators wonder why their tweaks aren't live.
    _send_static_file(
        handler, "service-worker.js",
        "application/javascript; charset=utf-8", "no-cache, max-age=0",
        extra_headers={"Service-Worker-Allowed": "/"})


_PWA_ICONS = {"pwa-192.png", "pwa-512.png"}


def h_pwa_icon(handler: "Handler", parsed: ParseResult) -> None:
    name = parsed.path.lstrip("/")
    if name not in _PWA_ICONS:
        handler._send_json({"ok": False, "error": "not found"}, status=404)
        return
    _send_static_file(handler, name, "image/png", "public, max-age=86400")
