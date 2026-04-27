"""Server-Sent Events endpoint for live session-list updates.

A long-lived ``GET /api/sessions/stream`` keeps the dashboard's
state fresh without periodic polling. The server polls
``_session_summary()`` once per second and pushes a `data:` event
only when the JSON payload differs from the last one sent — so an
idle dashboard generates near-zero traffic.

Why SSE rather than WebSocket: SSE is HTTP/1.0-compatible (works
through reverse proxies that don't speak Upgrade), unidirectional
(server → client) which exactly matches our use case, and
implementable on top of stdlib ``http.server`` without any new
dependency. The dashboard already runs ``ThreadingHTTPServer`` so
each subscriber gets its own thread; for a single-operator
dashboard that's the right shape.

The handler exits cleanly when the client disconnects (the
write raises ``BrokenPipeError`` / ``ConnectionResetError``),
so threads aren't leaked across browser-tab churn.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

if TYPE_CHECKING:
    from ..server import Handler


# Push interval. Server checks once per second whether the session
# summary changed; only differences emit `data:` events. One-second
# resolution feels live without burning CPU on a quiet dashboard.
_PUSH_INTERVAL_SEC = 1.0

# Heartbeat: if no real event has been emitted for this long, send
# a comment line (`:keepalive\n\n`) so the connection stays warm
# through proxies that drop idle TCP after ~30s.
_HEARTBEAT_INTERVAL_SEC = 25.0


def h_sessions_stream(handler: "Handler", _parsed: ParseResult) -> None:
    from ..server import _session_summary

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache, no-transform")
    handler.send_header("Connection", "keep-alive")
    # Some reverse proxies (notably nginx) buffer text/event-stream
    # by default; X-Accel-Buffering=no opts out for nginx, and other
    # proxies generally respect Cache-Control: no-transform.
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    last_payload: str | None = None
    last_emit_at = time.monotonic()

    try:
        while True:
            summary = _session_summary()
            payload = {
                "ok": True,
                "sessions": summary.rows,
                "tmux_unreachable": summary.tmux_unreachable,
            }
            wire = json.dumps(payload, separators=(",", ":"))
            now = time.monotonic()

            if wire != last_payload:
                handler.wfile.write(f"data: {wire}\n\n".encode("utf-8"))
                handler.wfile.flush()
                last_payload = wire
                last_emit_at = now
            elif (now - last_emit_at) >= _HEARTBEAT_INTERVAL_SEC:
                # Proxy keepalive: write an SSE comment line. The
                # browser ignores it; the TCP layer stays warm.
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                last_emit_at = now

            time.sleep(_PUSH_INTERVAL_SEC)
    except (BrokenPipeError, ConnectionResetError):
        # Client closed the tab or browser; clean exit.
        return
    except OSError:
        # Generic socket error during write — same disposition.
        return
