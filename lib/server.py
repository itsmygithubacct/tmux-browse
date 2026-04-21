"""HTTP handler and server entry. Stdlib only (http.server)."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import auth, config, ports, sessions, templates, tls as tls_mod, ttyd
from .targeting import Target


# Redact ``?token=…`` / ``&token=…`` from request lines before the stdlib
# logger writes them to stderr. Matters for --verbose mode where the initial
# bootstrap URL would otherwise land in logs. Uppercase match is defensive;
# tokens are compared case-sensitively but URLs commonly normalize.
_TOKEN_PARAM_RE = re.compile(r"([?&])token=[^&\s]*", re.IGNORECASE)


def _redact_token(s: str) -> str:
    return _TOKEN_PARAM_RE.sub(r"\1token=<redacted>", s)


def _session_summary() -> list[dict]:
    """Session list enriched with port assignment + ttyd running flag.

    Age fields are also computed server-side (``idle_seconds``,
    ``created_seconds_ago``) so the browser doesn't need to trust its
    own clock — useful across VMs or laptops waking from sleep.
    """
    now = int(time.time())
    assignments = ports.all_assignments()
    out: list[dict] = []
    for s in sessions.list_sessions():
        name = s["name"]
        port = assignments.get(name)
        pid = ttyd.read_pid(name)
        out.append({
            "name": name,
            "windows": s["windows"],
            "attached": s["attached"],
            "created": s["created"],
            "activity": s["activity"],
            "idle_seconds": max(0, now - s["activity"]),
            "created_seconds_ago": max(0, now - s["created"]),
            "port": port,
            "pid": pid,
            "ttyd_running": pid is not None,
        })
    return out


def _restart_self() -> None:
    """Re-exec the current dashboard process with its original argv."""
    time.sleep(0.15)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _write_dashboard_state(bind: str, port: int) -> None:
    payload = {
        "pid": os.getpid(),
        "bind": bind,
        "port": port,
        "started_at": int(time.time()),
    }
    config.DASHBOARD_FILE.write_text(json.dumps(payload))


def _clear_dashboard_state() -> None:
    try:
        raw = json.loads(config.DASHBOARD_FILE.read_text())
    except (OSError, ValueError):
        config.DASHBOARD_FILE.unlink(missing_ok=True)
        return
    if raw.get("pid") == os.getpid():
        config.DASHBOARD_FILE.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "tmux-browse/0.3.0"

    # Keep the default stderr logger quiet unless --verbose was used, and
    # redact any ``?token=`` before it hits stderr.
    def log_message(self, format, *args):
        if not getattr(self.server, "verbose", False):
            return
        redacted = tuple(
            _redact_token(a) if isinstance(a, str) else a for a in args
        )
        super().log_message(format, *redacted)

    # --- helpers -----------------------------------------------------------

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200) -> None:
        body = text.encode("utf-8", errors="replace")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # --- auth --------------------------------------------------------------

    def _auth_gate(self) -> bool:
        """Return True if the request may proceed; False after we've already
        sent a 401 or a redirect."""
        expected = getattr(self.server, "expected_token", None)
        if not expected:
            return True  # auth disabled
        parsed = urlparse(self.path)
        if auth.path_is_open(self.path):
            return True
        given = auth.extract_token(self)
        if auth.matches(expected, given):
            # If the token came via ?token=, strip it from the URL and
            # persist via cookie so future requests don't leak it in logs
            # or in the Referer header.
            query = parse_qs(parsed.query)
            if "token" in query and parsed.path == "/":
                cleaned = [f"{k}={v}" for k, vs in query.items()
                           if k != "token" for v in vs]
                new_query = "&".join(cleaned)
                location = parsed.path + (f"?{new_query}" if new_query else "")
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Set-Cookie", auth.make_cookie_header(expected))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False
            return True
        auth.send_401(self)
        return False

    # --- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if not self._auth_gate():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send_html(templates.render_index())
            return
        if path == "/api/sessions":
            self._send_json({"ok": True, "sessions": _session_summary()})
            return
        if path == "/api/ports":
            self._send_json({"ok": True, "assignments": ports.all_assignments()})
            return
        if path == "/api/session/log":
            query = parse_qs(parsed.query)
            name = (query.get("session", [""])[0] or "").strip()
            try:
                lines = int(query.get("lines", ["2000"])[0])
            except ValueError:
                lines = 2000
            lines = max(1, min(lines, 50000))
            if not name:
                self._send_text("missing 'session' query parameter", status=400)
                return
            ok, content = sessions.capture_target(Target(session=name), lines=lines)
            if not ok:
                self._send_text(content, status=404)
                return
            self._send_text(content)
            return
        if path == "/health":
            self._send_json({"ok": True})
            return
        self._send_json({"ok": False, "error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth_gate():
            return
        path = urlparse(self.path).path
        body = self._read_json()

        if path == "/api/ttyd/start":
            name = (body.get("session") or "").strip()
            if not name:
                self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
                return
            if not sessions.exists(name):
                self._send_json({"ok": False, "error": f"no such tmux session: {name}"},
                                status=404)
                return
            tls_paths = getattr(self.server, "tls_paths", None)
            self._send_json(ttyd.start(name, tls_paths=tls_paths))
            return

        if path == "/api/ttyd/stop":
            name = (body.get("session") or "").strip()
            if not name:
                self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
                return
            self._send_json(ttyd.stop(name))
            return

        if path == "/api/session/new":
            name = (body.get("name") or "").strip()
            ok, err = sessions.new_session(name)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
            self._send_json({"ok": True, "name": name})
            return

        if path == "/api/session/scroll":
            name = (body.get("session") or "").strip()
            if not name:
                self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
                return
            ok, err = sessions.enter_copy_mode(name)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
            self._send_json({"ok": True})
            return

        if path == "/api/session/type":
            name = (body.get("session") or "").strip()
            text = body.get("text")
            if not name:
                self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
                return
            if not isinstance(text, str) or not text.strip():
                self._send_json({"ok": False, "error": "missing 'text'"}, status=400)
                return
            ok, err = sessions.type_line(Target(session=name), text)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
            self._send_json({"ok": True})
            return

        if path == "/api/server/restart":
            self._send_json({"ok": True, "restarting": True})
            threading.Thread(target=_restart_self, daemon=True).start()
            return

        if path == "/api/session/kill":
            name = (body.get("session") or "").strip()
            if not name:
                self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
                return
            # Stop ttyd first so the wrapper exits cleanly, then kill tmux.
            ttyd.stop(name)
            ok, err = sessions.kill(name)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
            self._send_json({"ok": True})
            return

        self._send_json({"ok": False, "error": "not found"}, status=404)


def serve(bind: str, port: int, verbose: bool = False,
          expected_token: str | None = None,
          tls_paths: tuple[Path, Path] | None = None) -> None:
    config.ensure_dirs()
    _write_dashboard_state(bind, port)
    httpd = ThreadingHTTPServer((bind, port), Handler)
    httpd.verbose = verbose  # type: ignore[attr-defined]
    httpd.expected_token = expected_token  # type: ignore[attr-defined]
    httpd.tls_paths = tls_paths  # type: ignore[attr-defined]
    httpd.daemon_threads = True
    if tls_paths is not None:
        ctx = tls_mod.build_context(*tls_paths)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    scheme = "https" if tls_paths else "http"
    host_display = bind if bind not in ("0.0.0.0", "") else "0.0.0.0 (all interfaces)"
    print(f"tmux-browse dashboard listening on {scheme}://{host_display}:{port}/")
    print(f"  state dir: {config.STATE_DIR}")
    print(f"  ttyd port range: {config.TTYD_PORT_START}-{config.TTYD_PORT_END}")
    if tls_paths:
        cert, key = tls_paths
        print(f"  tls: ENABLED (cert={cert}, key={key}; ttyds inherit the same pair)")
    else:
        print("  tls: disabled (plain HTTP — anyone on the network can sniff traffic)")
    if expected_token:
        print("  auth: ENABLED (Bearer token required — see docs/dashboard.md)")
    else:
        print("  auth: disabled (any reachable client can access the dashboard)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        _clear_dashboard_state()
        httpd.server_close()
