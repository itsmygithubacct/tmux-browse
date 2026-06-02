"""Server-Sent Events endpoint for live session-list updates.

A long-lived ``GET /api/sessions/stream`` keeps the dashboard's
state fresh without periodic polling. A single shared producer thread
(``server._session_stream_hub``) computes ``_session_summary()`` at
most once per second and fans the result out to every subscriber, so
N open dashboard tabs cost one summary per tick, not N. A `data:`
event is emitted only when the payload changes — an idle dashboard
generates near-zero traffic.

Why SSE rather than WebSocket: SSE is HTTP/1.0-compatible (works
through reverse proxies that don't speak Upgrade), unidirectional
(server → client) which exactly matches our use case, and
implementable on top of stdlib ``http.server`` without any new
dependency. The dashboard already runs ``ThreadingHTTPServer`` so
each subscriber gets its own thread; now that thread just blocks on
the hub's condition variable rather than independently driving tmux.

The handler exits cleanly when the client disconnects (the write
raises ``BrokenPipeError`` / ``ConnectionResetError``) and always
unsubscribes from the hub, so threads aren't leaked and the producer
stops once the last subscriber leaves.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

if TYPE_CHECKING:
    from ..server import Handler


# Heartbeat: if no real event has been emitted for this long, send
# a comment line (`:keepalive\n\n`) so the connection stays warm
# through proxies that drop idle TCP after ~30s.
_HEARTBEAT_INTERVAL_SEC = 25.0


def h_sessions_stream(handler: "Handler", _parsed: ParseResult) -> None:
    from ..server import _session_stream_hub

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache, no-transform")
    handler.send_header("Connection", "keep-alive")
    # Some reverse proxies (notably nginx) buffer text/event-stream
    # by default; X-Accel-Buffering=no opts out for nginx, and other
    # proxies generally respect Cache-Control: no-transform.
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    version, payload = _session_stream_hub.subscribe()
    try:
        last_emit_at = time.monotonic()
        # Seed the connection with the current state so the tab renders
        # immediately instead of waiting for the next change.
        if payload is not None:
            handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            handler.wfile.flush()
        last_sent_version = version

        while True:
            version, payload = _session_stream_hub.wait(
                last_sent_version, timeout=_HEARTBEAT_INTERVAL_SEC)
            now = time.monotonic()
            if payload is not None and version > last_sent_version:
                handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                handler.wfile.flush()
                last_sent_version = version
                last_emit_at = now
            elif (now - last_emit_at) >= _HEARTBEAT_INTERVAL_SEC:
                # Proxy keepalive: write an SSE comment line. The
                # browser ignores it; the TCP layer stays warm.
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                last_emit_at = now
    except (BrokenPipeError, ConnectionResetError):
        # Client closed the tab or browser; clean exit.
        return
    except OSError:
        # Generic socket error during write — same disposition.
        return
    finally:
        _session_stream_hub.unsubscribe()
