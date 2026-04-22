"""HTTP handler and server entry. Stdlib only (http.server)."""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import MappingProxyType
from typing import Callable
from urllib.parse import ParseResult, parse_qs, urlparse

from . import (
    agent_logs,
    agent_store,
    agent_runtime,
    agent_workflows,
    auth,
    config,
    dashboard_config,
    ports,
    sessions,
    static,
    templates,
    tls as tls_mod,
    ttyd,
)
from .errors import TBError
from .targeting import Target


class DashboardServer(ThreadingHTTPServer):
    """Typed ``ThreadingHTTPServer`` subclass carrying our configuration.

    All attributes the ``Handler`` reads off ``self.server`` are declared
    here so tooling doesn't need ``# type: ignore[attr-defined]`` and the
    server/handler contract is legible at a glance.
    """

    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, *,
                 verbose: bool = False,
                 expected_token: str | None = None,
                 tls_paths: tuple[Path, Path] | None = None,
                 ttyd_bind_addr: str | None = None) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.verbose = verbose
        self.expected_token = expected_token
        self.tls_paths = tls_paths
        self.ttyd_bind_addr = ttyd_bind_addr


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
    try:
        configured_agents = {row["name"] for row in agent_store.list_agents()}
    except TBError:
        configured_agents = set()
    out: list[dict] = []
    for s in sessions.list_sessions():
        name = s["name"]
        port = assignments.get(name)
        pid = ttyd.read_pid(name)
        agent_name = agent_runtime.agent_name_from_session(name)
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
            "conversation_mode": bool(agent_name and agent_name in configured_agents),
            "agent_name": agent_name if agent_name in configured_agents else None,
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


from . import __version__


class Handler(BaseHTTPRequestHandler):
    server_version = f"tmux-browse/{__version__}"

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

    def _send_tb_error(self, err: TBError) -> None:
        status = 400 if err.exit_code == 2 else 500
        self._send_json({"ok": False, "error": err.message}, status=status)

    # --- auth --------------------------------------------------------------

    def _auth_gate(self) -> bool:
        """Return True if the request may proceed, False after we've sent
        a 401 or a 302 redirect.

        Composition: first decide whether the request is authenticated, then
        (on success) give the token-rewrite-redirect a chance to fire. Keeping
        these two concerns separate makes the code easier to reason about
        than the previous combined block.
        """
        expected = getattr(self.server, "expected_token", None)
        if not expected:
            return True  # auth disabled
        if auth.path_is_open(self.path):
            return True
        given = auth.extract_token(self)
        if not auth.matches(expected, given):
            auth.send_401(self)
            return False
        return not self._maybe_strip_token_redirect(expected)

    def _maybe_strip_token_redirect(self, token: str) -> bool:
        """If the request carried ``?token=…`` on the root path, 302 to the
        root with the token stripped and the token persisted as an HttpOnly
        cookie. Returns True when a redirect was sent (caller must not
        continue).

        Only fires on the root URL — API calls don't participate in Referer
        chains, so the extra round-trip isn't worth it for them.
        """
        parsed = urlparse(self.path)
        if parsed.path != "/":
            return False
        query = parse_qs(parsed.query)
        if "token" not in query:
            return False
        cleaned = [f"{k}={v}" for k, vs in query.items()
                   if k != "token" for v in vs]
        new_query = "&".join(cleaned)
        location = parsed.path + (f"?{new_query}" if new_query else "")
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Set-Cookie", auth.make_cookie_header(token))
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    # --- per-route handlers ------------------------------------------------
    # Each method handles one route. GET handlers take (parsed_url);
    # POST handlers take (parsed_url, body_dict). The dispatch tables at
    # the bottom of the class map paths to these. Adding a new route
    # means: write a _handle_* method, add one line to the table.

    def _h_index(self, _parsed: ParseResult) -> None:
        self._send_html(templates.render_index())

    def _h_favicon(self, _parsed: ParseResult) -> None:
        body = static.FAVICON_SVG.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def _h_raw_ttyd(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        name = (query.get("name", [""])[0] or "").strip()
        scheme = (query.get("scheme", [""])[0] or "").strip().lower()
        try:
            port = int(query.get("port", ["0"])[0])
        except ValueError:
            port = 0
        if not name or port <= 0:
            self._send_json({"ok": False, "error": "missing raw ttyd name or port"}, status=400)
            return
        if scheme not in {"http", "https"}:
            scheme = "http"
        self._send_html(templates.render_raw_ttyd(name, port, scheme))

    def _h_sessions(self, _parsed: ParseResult) -> None:
        self._send_json({"ok": True, "sessions": _session_summary()})

    def _h_ports(self, _parsed: ParseResult) -> None:
        self._send_json({"ok": True, "assignments": ports.all_assignments()})

    def _h_dashboard_config_get(self, _parsed: ParseResult) -> None:
        self._send_json({
            "ok": True,
            "config": dashboard_config.load(),
            "path": str(config.DASHBOARD_CONFIG_FILE),
        })

    def _h_agents_get(self, _parsed: ParseResult) -> None:
        try:
            self._send_json({
                "ok": True,
                "agents": agent_store.list_agents(),
                "defaults": agent_store.catalog_rows(),
                "paths": {
                    "agents": str(agent_store.AGENTS_FILE),
                    "secrets": str(agent_store.SECRETS_FILE),
                    "logs": str(config.AGENT_LOG_DIR),
                    "workflows": str(config.AGENT_WORKFLOWS_FILE),
                },
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_log(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        name = (query.get("name", [""])[0] or "").strip().lower()
        try:
            limit = int(query.get("limit", ["200"])[0])
        except ValueError:
            limit = 200
        limit = max(1, min(limit, 1000))
        if not name:
            self._send_text("missing 'name' query parameter", status=400)
            return
        try:
            self._send_text(agent_logs.render_text(name, limit=limit))
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_log_json(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        name = (query.get("name", [""])[0] or "").strip().lower()
        try:
            limit = int(query.get("limit", ["20"])[0])
        except ValueError:
            limit = 20
        limit = max(1, min(limit, 100))
        if not name:
            self._send_json({"ok": False, "error": "missing 'name' query parameter"}, status=400)
            return
        try:
            self._send_json({
                "ok": True,
                "name": name,
                "entries": agent_logs.read_entries(name, limit=limit),
                "path": str(agent_logs.log_path(name)),
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_workflows_get(self, _parsed: ParseResult) -> None:
        try:
            self._send_json({
                "ok": True,
                "config": agent_workflows.load(),
                "path": str(config.AGENT_WORKFLOWS_FILE),
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_session_log(self, parsed: ParseResult) -> None:
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

    def _h_health(self, _parsed: ParseResult) -> None:
        self._send_json({"ok": True})

    # --- POST handlers ----

    def _h_ttyd_start(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("session") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        if not sessions.exists(name):
            self._send_json({"ok": False, "error": f"no such tmux session: {name}"},
                            status=404)
            return
        tls_paths = getattr(self.server, "tls_paths", None)
        bind_addr = getattr(self.server, "ttyd_bind_addr", None)
        self._send_json(ttyd.start(name, tls_paths=tls_paths, bind_addr=bind_addr))

    def _h_ttyd_raw(self, _parsed: ParseResult, _body: dict) -> None:
        tls_paths = getattr(self.server, "tls_paths", None)
        bind_addr = getattr(self.server, "ttyd_bind_addr", None)
        self._send_json(ttyd.start_raw(tls_paths=tls_paths, bind_addr=bind_addr))

    def _h_ttyd_stop(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("session") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        self._send_json(ttyd.stop(name))

    def _h_session_new(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("name") or "").strip()
        ok, err = sessions.new_session(name)
        if not ok:
            self._send_json({"ok": False, "error": err}, status=400)
            return
        self._send_json({"ok": True, "name": name})

    def _h_session_scroll(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("session") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        ok, err = sessions.enter_copy_mode(name)
        if not ok:
            self._send_json({"ok": False, "error": err}, status=400)
            return
        self._send_json({"ok": True})

    def _h_session_type(self, _parsed: ParseResult, body: dict) -> None:
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

    def _h_dashboard_config_post(self, _parsed: ParseResult, body: dict) -> None:
        payload = body.get("config", body)
        saved = dashboard_config.save(payload)
        self._send_json({
            "ok": True,
            "config": saved,
            "path": str(config.DASHBOARD_CONFIG_FILE),
        })

    def _h_agents_post(self, _parsed: ParseResult, body: dict) -> None:
        payload = body.get("agent", body)
        name = (payload.get("name") or "").strip()
        api_key = payload.get("api_key")
        if not isinstance(api_key, str):
            api_key = None
        elif not api_key.strip():
            api_key = None
        try:
            row = agent_store.save_agent(
                name,
                api_key=api_key,
                model=(payload.get("model") or "").strip() or None,
                base_url=(payload.get("base_url") or "").strip() or None,
                provider=(payload.get("provider") or "").strip() or None,
                wire_api=(payload.get("wire_api") or "").strip() or None,
            )
        except TBError as e:
            self._send_tb_error(e)
            return
        self._send_json({"ok": True, "agent": row})

    def _h_agents_remove(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'name'"}, status=400)
            return
        try:
            removed = agent_store.remove_agent(name)
        except TBError as e:
            self._send_tb_error(e)
            return
        self._send_json({"ok": True, "removed": removed, "name": name})

    def _h_agent_workflows_post(self, _parsed: ParseResult, body: dict) -> None:
        payload = body.get("config", body)
        try:
            saved = agent_workflows.save(payload)
        except TBError as e:
            self._send_tb_error(e)
            return
        self._send_json({
            "ok": True,
            "config": saved,
            "path": str(config.AGENT_WORKFLOWS_FILE),
        })

    def _h_agent_conversation_open(self, _parsed: ParseResult, body: dict) -> None:
        agent_name = (body.get("name") or "").strip().lower()
        if not agent_name:
            self._send_json({"ok": False, "error": "missing 'name'"}, status=400)
            return
        try:
            agent_store.get_agent(agent_name)
        except TBError as e:
            self._send_tb_error(e)
            return
        session_name = agent_runtime.conversation_session_name(agent_name)
        if not sessions.exists(session_name):
            cmd = " ".join([
                shlex.quote(sys.executable),
                "-u",
                shlex.quote(str(config.PROJECT_DIR / "tb.py")),
                "agent",
                "repl",
                shlex.quote(agent_name),
            ])
            ok, err = sessions.new_session(session_name, cwd=str(config.PROJECT_DIR), cmd=cmd)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
        tls_paths = getattr(self.server, "tls_paths", None)
        bind_addr = getattr(self.server, "ttyd_bind_addr", None)
        ttyd_result = ttyd.start(session_name, tls_paths=tls_paths, bind_addr=bind_addr)
        if not ttyd_result.get("ok"):
            self._send_json(ttyd_result, status=400)
            return
        self._send_json({
            "ok": True,
            "agent": agent_name,
            "session": session_name,
            "port": ttyd_result.get("port"),
            "scheme": ttyd_result.get("scheme", "http"),
            "url": f"{ttyd_result.get('scheme', 'http')}://localhost:{ttyd_result.get('port')}/",
            "already": ttyd_result.get("already", False),
        })

    def _h_server_restart(self, _parsed: ParseResult, _body: dict) -> None:
        self._send_json({"ok": True, "restarting": True})
        threading.Thread(target=_restart_self, daemon=True).start()

    def _h_session_kill(self, _parsed: ParseResult, body: dict) -> None:
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

    # --- dispatch ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if not self._auth_gate():
            return
        parsed = urlparse(self.path)
        handler = self._GET_ROUTES.get(parsed.path)
        if handler is None:
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        handler(self, parsed)

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth_gate():
            return
        parsed = urlparse(self.path)
        handler = self._POST_ROUTES.get(parsed.path)
        if handler is None:
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        body = self._read_json()
        handler(self, parsed, body)

    # --- route tables ------------------------------------------------------
    # Declared last so every method name they reference is bound in the
    # class namespace at class-body evaluation time. Wrapped in MappingProxyType
    # so a subclass or mistaken `Handler._GET_ROUTES["/x"] = ...` at runtime
    # fails loudly (TypeError) instead of silently mutating dispatch.
    _GET_ROUTES: MappingProxyType[str, Callable[["Handler", ParseResult], None]] = MappingProxyType({
        "/":                       _h_index,
        "/favicon.ico":            _h_favicon,
        "/favicon.svg":            _h_favicon,
        "/raw-ttyd":               _h_raw_ttyd,
        "/api/sessions":           _h_sessions,
        "/api/ports":              _h_ports,
        "/api/dashboard-config":   _h_dashboard_config_get,
        "/api/agents":             _h_agents_get,
        "/api/agent-log":          _h_agent_log,
        "/api/agent-log-json":     _h_agent_log_json,
        "/api/agent-workflows":    _h_agent_workflows_get,
        "/api/session/log":        _h_session_log,
        "/health":                 _h_health,
    })
    _POST_ROUTES: MappingProxyType[str, Callable[["Handler", ParseResult, dict], None]] = MappingProxyType({
        "/api/ttyd/start":         _h_ttyd_start,
        "/api/ttyd/raw":           _h_ttyd_raw,
        "/api/ttyd/stop":          _h_ttyd_stop,
        "/api/session/new":        _h_session_new,
        "/api/session/scroll":     _h_session_scroll,
        "/api/session/type":       _h_session_type,
        "/api/dashboard-config":   _h_dashboard_config_post,
        "/api/agents":             _h_agents_post,
        "/api/agents/remove":      _h_agents_remove,
        "/api/agent-workflows":    _h_agent_workflows_post,
        "/api/agent-conversation": _h_agent_conversation_open,
        "/api/server/restart":     _h_server_restart,
        "/api/session/kill":       _h_session_kill,
    })


def serve(bind: str, port: int, verbose: bool = False,
          expected_token: str | None = None,
          tls_paths: tuple[Path, Path] | None = None) -> None:
    config.ensure_dirs()

    # Startup GC: previous dashboard may have exited hard (SIGKILL / crash)
    # leaving pidfiles for ttyds whose processes are dead, or port
    # assignments for sessions that no longer exist. Both leak port slots
    # over time.
    try:
        gc_stats = ttyd.gc_orphans()
        if gc_stats["stale_pids_removed"] or gc_stats["ports_dropped"]:
            print(f"  startup gc: removed {gc_stats['stale_pids_removed']} dead "
                  f"pidfiles, dropped {gc_stats['ports_dropped']} stale ports")
    except Exception as e:  # never let GC failure block startup
        print(f"  startup gc: skipped ({e})")

    _write_dashboard_state(bind, port)
    httpd = DashboardServer(
        (bind, port), Handler,
        verbose=verbose,
        expected_token=expected_token,
        tls_paths=tls_paths,
        ttyd_bind_addr=bind,
    )
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

    # Graceful shutdown on SIGTERM (systemd, container runtimes, kill).
    # serve_forever() only breaks on KeyboardInterrupt out of the box;
    # moving it to a worker thread lets the main thread wait on an Event
    # that either signal (SIGTERM or SIGINT) sets. This preserves Ctrl-C
    # interactive behavior AND responds to `systemctl stop`.
    shutdown_event = threading.Event()

    def _on_signal(signum, _frame):
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    try:
        shutdown_event.wait()
    finally:
        print("\nshutting down")
        httpd.shutdown()             # unblocks serve_forever()
        server_thread.join(timeout=5)
        _clear_dashboard_state()
        httpd.server_close()
