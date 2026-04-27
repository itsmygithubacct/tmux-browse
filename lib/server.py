"""HTTP handler and server entry. Stdlib only (http.server)."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import MappingProxyType
from typing import Callable
from urllib.parse import ParseResult, parse_qs, urlparse

from .server_routes import meta as routes_meta
from . import (
    auth,
    tasks as tasks_mod,
    config,
    dashboard_config,
    session_logs,
    extensions,
    ports,
    sessions,
    static,
    templates,
    tls as tls_mod,
    ttyd,
)
from .extensions import MergedRegistry, RegistryConflict
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
        # Populated by the agent extension's startup hook when enabled.
        self.scheduler = None
        # Extensions load once at server start; Handler reads their
        # routes / slots / JS off ``self.server.extension_registry``.
        self.extension_registry: MergedRegistry = MergedRegistry()


# Redact ``?token=…`` / ``&token=…`` from request lines before the stdlib
# logger writes them to stderr. Matters for --verbose mode where the initial
# bootstrap URL would otherwise land in logs. Uppercase match is defensive;
# tokens are compared case-sensitively but URLs commonly normalize.
_TOKEN_PARAM_RE = re.compile(r"([?&])token=[^&\s]*", re.IGNORECASE)


def _redact_token(s: str) -> str:
    return _TOKEN_PARAM_RE.sub(r"\1token=<redacted>", s)


@dataclass
class SessionSummary:
    """Result of :func:`_session_summary` — the rows the dashboard renders
    plus any out-of-band degradation flags. New flags should be added as
    fields here rather than expanding the return tuple, so callers and
    tests don't have to track positional shape changes.
    """
    rows: list[dict] = field(default_factory=list)
    tmux_unreachable: bool = False


def _session_summary() -> SessionSummary:
    """Session list enriched with port assignment + ttyd running flag.

    ``SessionSummary.tmux_unreachable`` is True when tmux's socket exists
    but the server isn't responding — the dashboard surfaces a banner so
    operators don't see "0 sessions" and assume the session list is
    authoritative. Raw-shell rows are still returned in that case (their
    state lives in the port registry, not tmux).

    Age fields are also computed server-side (``idle_seconds``,
    ``created_seconds_ago``) so the browser doesn't need to trust its
    own clock — useful across VMs or laptops waking from sleep.
    """
    now = int(time.time())
    # Cheap probe before the heavier list-sessions call — if tmux is
    # unresponsive, every subsequent tmux subprocess will eat its full
    # timeout budget. Skip them and report degradation instead.
    tmux_unreachable = not sessions.server_responsive()
    if not tmux_unreachable:
        # Ensure pipe-pane logging is active for every session — cheap and
        # throttled internally, so calling on every request is fine. This
        # catches panes/windows that were added after the session was created.
        try:
            session_logs.ensure_logging_all()
        except Exception:
            # Logging best-effort — don't fail the whole request because
            # one tmux pipe-pane call hiccuped.
            pass
    assignments = ports.all_assignments()
    # Agent metadata is only populated when the agent extension is loaded;
    # core treats its absence as "no agents configured".
    try:
        from agent import store as agent_store, runtime as agent_runtime
    except ImportError:
        agent_store = agent_runtime = None
    configured_agents: set[str] = set()
    if agent_store is not None:
        try:
            configured_agents = {row["name"] for row in agent_store.list_agents()}
        except TBError:
            pass
    out: list[dict] = []
    tmux_names: set[str] = set()
    tmux_rows = [] if tmux_unreachable else sessions.list_sessions()
    for s in tmux_rows:
        name = s["name"]
        tmux_names.add(name)
        port = assignments.get(name)
        pid = ttyd.read_pid(name)
        agent_name = agent_runtime.agent_name_from_session(name) if agent_runtime is not None else None
        # Prefer hash-based idle from the session log; fall back to
        # tmux's session_activity if no log exists yet.
        hash_idle = session_logs.idle_seconds(name, now=now)
        idle = hash_idle if hash_idle is not None else max(0, now - s["activity"])
        out.append({
            "name": name,
            "kind": "tmux",
            "windows": s["windows"],
            "attached": s["attached"],
            "created": s["created"],
            "activity": s["activity"],
            "idle_seconds": idle,
            "created_seconds_ago": max(0, now - s["created"]),
            "port": port,
            "pid": pid,
            "ttyd_running": pid is not None,
            "conversation_mode": bool(agent_name and agent_name in configured_agents),
            "agent_name": agent_name if agent_name in configured_agents else None,
        })
    # Raw ttyd shells aren't tmux sessions but the dashboard treats them
    # as peer panes (movable/snap-able alongside tmux ones). Surface any
    # name with a port assignment + live pidfile that isn't a tmux session
    # — by convention these are ``raw-shell-*``.
    for name, port in assignments.items():
        if name in tmux_names or not name.startswith("raw-shell-"):
            continue
        pid = ttyd.read_pid(name)
        if pid is None:
            continue
        out.append({
            "name": name,
            "kind": "raw",
            "windows": 0,
            "attached": False,
            "created": now,
            "activity": now,
            "idle_seconds": 0,
            "created_seconds_ago": 0,
            "port": port,
            "pid": pid,
            "ttyd_running": True,
            "conversation_mode": False,
            "agent_name": None,
        })
    return SessionSummary(rows=out, tmux_unreachable=tmux_unreachable)


# --- Connected client tracking ---

_CLIENT_TIMEOUT = 60  # seconds before a client is considered gone
_clients: dict[str, dict] = {}  # keyed by client_id
_client_inbox: dict[str, list[dict]] = {}  # keyed by client_id


def _client_id(ip: str, ua: str) -> str:
    """Stable-ish fingerprint for a browser session."""
    import hashlib
    return hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:12]


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _log_html(name: str, content: str) -> str:
    """Wrap a plain-text scrollback in an HTML page that scrolls to
    the bottom on load — operator's eye lands on the most recent
    output instead of the top of the buffer."""
    title = _html_escape(f"log · {name}")
    body = _html_escape(content)
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title>"
        "<style>html,body{margin:0;background:#0d1117;color:#e6edf3;}"
        "pre{margin:0;padding:0.6rem 0.9rem;font:13px/1.4 ui-monospace,"
        "SFMono-Regular,Menlo,Consolas,monospace;white-space:pre;"
        "min-height:100vh;}</style></head><body>"
        f"<pre id=\"log\">{body}</pre>"
        "<script>window.scrollTo(0, document.body.scrollHeight);</script>"
        "</body></html>"
    )


def _log_error_html(name: str, msg: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>log · {_html_escape(name)} (error)</title></head>"
        "<body style=\"font:14px ui-monospace,monospace;background:#0d1117;color:#f85149;padding:1rem\">"
        f"<pre>{_html_escape(msg)}</pre></body></html>"
    )


def _touch_client(handler: "Handler") -> str:
    """Record a client heartbeat. Returns the client_id."""
    ip = handler.client_address[0]
    ua = handler.headers.get("User-Agent", "")
    cid = _client_id(ip, ua)
    now = int(time.time())
    entry = _clients.get(cid, {})
    entry["client_id"] = cid
    entry["ip"] = ip
    entry["user_agent"] = ua
    entry["last_seen"] = now
    entry.setdefault("first_seen", now)
    entry.setdefault("nickname", "")
    _clients[cid] = entry
    return cid


def _active_clients() -> list[dict]:
    now = int(time.time())
    result = []
    for cid, entry in list(_clients.items()):
        age = now - entry.get("last_seen", 0)
        if age > _CLIENT_TIMEOUT:
            _clients.pop(cid, None)
            _client_inbox.pop(cid, None)
            continue
        result.append({
            "client_id": cid,
            "ip": entry["ip"],
            "nickname": entry.get("nickname", ""),
            "last_seen": entry["last_seen"],
            "first_seen": entry.get("first_seen", 0),
            "idle_seconds": age,
        })
    return sorted(result, key=lambda c: c["last_seen"], reverse=True)


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


# -----------------------------------------------------------------------------
# Config-lock unlock tokens
# -----------------------------------------------------------------------------
#
# When the config-lock is set, mutating endpoints require an unlock token.
# The token is issued on a successful ``/api/config-lock/verify`` and held
# in-memory only — server restart forces re-unlock, which is acceptable for
# the single-user / small-LAN threat model this gate exists for. Tokens are
# compared with ``hmac.compare_digest`` to avoid timing leaks.

_UNLOCK_TOKEN_TTL_SEC = 12 * 3600
_unlock_tokens: dict[str, int] = {}  # token -> expiry epoch

# Extensions installed or enabled since this server started but not yet
# running live routes / UI. The Config pane surfaces a restart banner
# while this is non-empty. Cleared on server restart (it's in-memory by
# design — the real source of truth is whether the extension is loaded).
_extensions_pending_restart: dict[str, bool] = {}


def _issue_unlock_token(now: int | None = None) -> str:
    import secrets
    if now is None:
        now = int(time.time())
    # Prune expired entries opportunistically so the dict doesn't grow.
    for k in [k for k, exp in _unlock_tokens.items() if exp <= now]:
        _unlock_tokens.pop(k, None)
    token = secrets.token_urlsafe(32)
    _unlock_tokens[token] = now + _UNLOCK_TOKEN_TTL_SEC
    return token


def _unlock_token_valid(token: str, now: int | None = None) -> bool:
    import hmac
    if not token:
        return False
    if now is None:
        now = int(time.time())
    for known, exp in list(_unlock_tokens.items()):
        if exp <= now:
            _unlock_tokens.pop(known, None)
            continue
        if hmac.compare_digest(known, token):
            return True
    return False


def _lock_is_active() -> bool:
    try:
        return bool(config.CONFIG_LOCK_FILE.exists()
                    and config.CONFIG_LOCK_FILE.read_text(encoding="utf-8").strip())
    except OSError:
        return False


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

    def _check_unlock(self) -> bool:
        """Gate for mutating endpoints. Returns True when the request may
        proceed; sends 403 and returns False when the config lock is set
        and no valid unlock token is presented.

        Called at the top of each gated POST handler. Reads are never gated.
        """
        if not _lock_is_active():
            return True
        token = (self.headers.get("X-TB-Unlock-Token") or "").strip()
        if _unlock_token_valid(token):
            return True
        self._send_json({"ok": False, "error": "config locked"}, status=403)
        return False

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

    def _h_index(self, parsed: ParseResult) -> None:
        routes_meta.h_index(self, parsed)

    def _h_favicon(self, parsed: ParseResult) -> None:
        routes_meta.h_favicon(self, parsed)

    def _h_sessions(self, _parsed: ParseResult) -> None:
        summary = _session_summary()
        self._send_json({
            "ok": True,
            "sessions": summary.rows,
            "tmux_unreachable": summary.tmux_unreachable,
        })

    def _h_ports(self, _parsed: ParseResult) -> None:
        self._send_json({"ok": True, "assignments": ports.all_assignments()})

    def _h_dashboard_config_get(self, _parsed: ParseResult) -> None:
        self._send_json({
            "ok": True,
            "config": dashboard_config.load(),
            "path": str(config.DASHBOARD_CONFIG_FILE),
        })


    def _h_session_log(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        name = (query.get("session", [""])[0] or "").strip()
        try:
            lines = int(query.get("lines", ["2000"])[0])
        except ValueError:
            lines = 2000
        lines = max(1, min(lines, 50000))
        # ``html=1`` wraps the scrollback in a minimal HTML page that
        # auto-scrolls to the bottom. The dashboard's Log buttons pass
        # this so the operator lands at the most recent output instead
        # of the top of the file. Without the flag the response stays
        # ``text/plain`` for any scripted callers.
        as_html = (query.get("html", ["0"])[0] or "0").strip().lower() in ("1", "true", "yes")
        if not name:
            self._send_text("missing 'session' query parameter", status=400)
            return
        ok, content = sessions.capture_target(Target(session=name), lines=lines)
        if not ok:
            if as_html:
                self._send_html(_log_error_html(name, content), status=404)
            else:
                self._send_text(content, status=404)
            return
        if as_html:
            self._send_html(_log_html(name, content))
            return
        self._send_text(content)

    def _h_health(self, parsed: ParseResult) -> None:
        routes_meta.h_health(self, parsed)

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

    @staticmethod
    def _resolve_launch_cmd(cmd: str | None) -> str | None:
        if not cmd:
            return None
        if cmd == "sysmon":
            return f"bash {config.PROJECT_DIR / 'bin' / 'sysmon.sh'}"
        if cmd == "systop":
            for tool in ("glances", "htop", "btop", "top"):
                if shutil.which(tool):
                    return tool
            # Fallback: run sysmon with a message
            return (f"echo 'No top/htop/glances found. "
                    f"Install: apt install htop glances'; "
                    f"bash {config.PROJECT_DIR / 'bin' / 'sysmon.sh'}")
        return cmd

    def _h_session_new(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("name") or "").strip()
        cmd = self._resolve_launch_cmd((body.get("cmd") or "").strip() or None)
        cwd = (body.get("cwd") or "").strip() or None
        ok, err = sessions.new_session(name, cwd=cwd, cmd=cmd)
        if not ok:
            self._send_json({"ok": False, "error": err}, status=400)
            return
        # Auto-start ttyd if requested
        if body.get("launch_ttyd"):
            tls_paths = getattr(self.server, "tls_paths", None)
            bind_addr = getattr(self.server, "ttyd_bind_addr", None)
            ttyd_result = ttyd.start(name, tls_paths=tls_paths, bind_addr=bind_addr)
            self._send_json({"ok": True, "name": name,
                             "port": ttyd_result.get("port"),
                             "url": ttyd_result.get("url", "")})
            return
        self._send_json({"ok": True, "name": name})

    def _h_session_resize(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("session") or "").strip()
        cols = int(body.get("cols") or 0)
        # ``rows`` is optional — old callers only sent ``cols`` and got a
        # window-width-only resize; the new fit-to-iframe button on the
        # dashboard sends both so the terminal actually fills its
        # container vertically too.
        rows = int(body.get("rows") or 0)
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        if cols < 20 or cols > 500:
            self._send_json({"ok": False, "error": "cols must be 20-500"}, status=400)
            return
        if rows and (rows < 5 or rows > 200):
            self._send_json({"ok": False, "error": "rows must be 5-200"}, status=400)
            return
        import subprocess
        argv = ["tmux", "resize-window", "-t", f"={name}", "-x", str(cols)]
        if rows:
            argv += ["-y", str(rows)]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            self._send_json({"ok": False, "error": r.stderr.strip() or "resize failed"}, status=400)
            return
        self._send_json({"ok": True, "cols": cols, "rows": rows or None})

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

    def _h_session_zoom(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("session") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        ok, err = sessions.zoom_pane(name)
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

    def _h_session_key(self, _parsed: ParseResult, body: dict) -> None:
        name = (body.get("session") or "").strip()
        keys = body.get("keys")
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        if not isinstance(keys, list) or not keys:
            self._send_json({"ok": False, "error": "missing 'keys' (list of tmux key names)"}, status=400)
            return
        ok, err = sessions.send_keys(Target(session=name), *[str(k) for k in keys])
        if not ok:
            self._send_json({"ok": False, "error": err}, status=400)
            return
        self._send_json({"ok": True})

    def _h_dashboard_config_post(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        payload = body.get("config", body)
        saved = dashboard_config.save(payload)
        self._send_json({
            "ok": True,
            "config": saved,
            "path": str(config.DASHBOARD_CONFIG_FILE),
        })


    def _h_clients(self, _parsed: ParseResult) -> None:
        my_id = _touch_client(self)
        self._send_json({
            "ok": True,
            "clients": _active_clients(),
            "you": my_id,
        })

    def _h_clients_nickname(self, _parsed: ParseResult, body: dict) -> None:
        cid = _touch_client(self)
        nickname = (body.get("nickname") or "").strip()[:30]
        if cid in _clients:
            _clients[cid]["nickname"] = nickname
        self._send_json({"ok": True, "client_id": cid, "nickname": nickname})

    def _h_clients_send_config(self, _parsed: ParseResult, body: dict) -> None:
        my_id = _touch_client(self)
        target_id = (body.get("target") or "").strip()
        config_url = (body.get("config_url") or "").strip()
        if not target_id or not config_url:
            self._send_json({"ok": False, "error": "missing target or config_url"}, status=400)
            return
        if target_id not in _clients:
            self._send_json({"ok": False, "error": "target client not connected"}, status=404)
            return
        inbox = _client_inbox.setdefault(target_id, [])
        sender = _clients.get(my_id, {})
        inbox.append({
            "from": sender.get("nickname") or sender.get("ip", "unknown"),
            "from_id": my_id,
            "config_url": config_url,
            "ts": int(time.time()),
        })
        # Keep inbox bounded
        if len(inbox) > 10:
            inbox[:] = inbox[-10:]
        self._send_json({"ok": True, "sent": True})

    def _h_clients_inbox(self, _parsed: ParseResult) -> None:
        cid = _touch_client(self)
        messages = _client_inbox.pop(cid, [])
        self._send_json({"ok": True, "messages": messages})

    def _h_config_lock_status(self, _parsed: ParseResult) -> None:
        has_lock = config.CONFIG_LOCK_FILE.exists() and config.CONFIG_LOCK_FILE.read_text(encoding="utf-8").strip()
        self._send_json({"ok": True, "locked": bool(has_lock)})

    def _h_config_lock_set(self, _parsed: ParseResult, body: dict) -> None:
        # Setting or clearing the lock must itself be gated when a lock is
        # already active — otherwise anyone on the LAN could wipe it.
        if not self._check_unlock():
            return
        password = (body.get("password") or "").strip()
        if not password:
            # Clear the lock
            try:
                config.CONFIG_LOCK_FILE.unlink(missing_ok=True)
            except OSError:
                pass
            # Drop every issued token on clear so they can't be reused.
            _unlock_tokens.clear()
            self._send_json({"ok": True, "locked": False})
            return
        import hashlib
        hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
        config.ensure_dirs()
        config.CONFIG_LOCK_FILE.write_text(hashed + "\n", encoding="utf-8")
        try:
            config.CONFIG_LOCK_FILE.chmod(0o600)
        except OSError:
            pass
        self._send_json({"ok": True, "locked": True})

    def _h_config_lock_verify(self, _parsed: ParseResult, body: dict) -> None:
        password = (body.get("password") or "").strip()
        if not config.CONFIG_LOCK_FILE.exists():
            self._send_json({"ok": True, "unlocked": True})
            return
        stored = config.CONFIG_LOCK_FILE.read_text(encoding="utf-8").strip()
        if not stored:
            self._send_json({"ok": True, "unlocked": True})
            return
        import hashlib
        attempt = hashlib.sha256(password.encode("utf-8")).hexdigest()
        import hmac
        if hmac.compare_digest(stored, attempt):
            token = _issue_unlock_token()
            self._send_json({
                "ok": True, "unlocked": True,
                "unlock_token": token,
                "ttl_seconds": _UNLOCK_TOKEN_TTL_SEC,
            })
        else:
            self._send_json({"ok": False, "error": "wrong password"}, status=403)

    # --- Extensions --------------------------------------------------------
    # Status + enable/disable landed in E0 as real; install landed in E3.
    # Uninstall stays stubbed until E4's manage modal lands.

    def _h_extensions_status(self, _parsed: ParseResult) -> None:
        rows = extensions.status()
        catalog = extensions.CATALOG
        # Decorate each row with catalog metadata and submodule flag so
        # the Config pane's Extensions card has everything it needs in
        # one response (label, description, repo URL, submodule hint).
        by_name = {r["name"]: r for r in rows}
        for name, entry in catalog.items():
            row = by_name.get(name)
            if row is None:
                row = {
                    "name": name,
                    "installed": False,
                    "enabled": False,
                    "path": None,
                    "version": None,
                    "last_error": None,
                }
                rows.append(row)
                by_name[name] = row
            row["label"] = entry["label"]
            row["description"] = entry["description"]
            row["repo"] = entry["repo"]
            row["submodule"] = extensions.submodule.is_submodule_path(name)
            row["restart_pending"] = bool(
                _extensions_pending_restart.get(name))
        self._send_json({"ok": True, "extensions": rows})

    def _h_extensions_available(self, _parsed: ParseResult) -> None:
        # Catalog entries rendered as a simple install-target list for
        # clients that want just "what could I install" without mingling
        # with on-disk status.
        available = [dict(v) for v in extensions.CATALOG.values()]
        self._send_json({"ok": True, "available": available})

    def _h_extensions_install(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        name = (body.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'name'"},
                            status=400)
            return
        if name not in extensions.CATALOG:
            self._send_json(
                {"ok": False,
                 "error": f"unknown extension {name!r}",
                 "stage": "unknown"},
                status=400)
            return
        try:
            result = extensions.install(name)
        except extensions.InstallError as e:
            self._send_json(
                {"ok": False, "error": e.msg, "stage": e.stage},
                status=500)
            return
        # Flip the enabled bit so the next restart activates the surface.
        extensions.enable(name)
        _extensions_pending_restart[name] = True
        self._send_json({
            "ok": True,
            "name": name,
            "version": result.version,
            "via": result.via,
            "restart_required": True,
            "message": ("Installed and enabled. Restart the dashboard to "
                        "activate the extension's routes and UI."),
        })

    def _h_extensions_uninstall(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        name = (body.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'name'"},
                            status=400)
            return
        remove_state = bool(body.get("remove_state"))
        try:
            summary = extensions.uninstall(name, remove_state=remove_state)
        except Exception as e:  # noqa: broad — surface every failure
            self._send_json(
                {"ok": False, "error": str(e), "stage": "uninstall"},
                status=500)
            return
        _extensions_pending_restart[name] = True
        self._send_json({
            "ok": True,
            "name": name,
            "restart_required": True,
            "summary": summary,
            "message": ("Uninstalled. Restart the dashboard to remove the "
                        "extension's routes and UI."),
        })

    def _h_extensions_update(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        name = (body.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'name'"},
                            status=400)
            return
        try:
            result = extensions.update(name)
        except extensions.UpdateError as e:
            self._send_json(
                {"ok": False, "error": e.msg, "stage": e.stage},
                status=500)
            return
        if result.changed:
            _extensions_pending_restart[name] = True
        self._send_json({
            "ok": True,
            "name": name,
            "from_version": result.from_version,
            "to_version": result.to_version,
            "changed": result.changed,
            "via": result.via,
            "restart_required": result.changed,
            "message": (
                f"Updated {name} {result.from_version} → {result.to_version}. "
                "Restart the dashboard to activate."
                if result.changed else
                f"{name} is already at {result.to_version}."),
        })

    def _h_extensions_enable(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        name = (body.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'name'"},
                            status=400)
            return
        entry = extensions.enable(name)
        _extensions_pending_restart[name] = True
        self._send_json({
            "ok": True, "name": name, "entry": entry,
            "restart_required": True,
            "note": ("restart the dashboard to activate the extension's "
                     "routes and UI"),
        })

    def _h_extensions_disable(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        name = (body.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "missing 'name'"},
                            status=400)
            return
        entry = extensions.disable(name)
        _extensions_pending_restart[name] = True
        self._send_json({
            "ok": True, "name": name, "entry": entry,
            "restart_required": True,
        })

    def _h_tasks_get(self, _parsed: ParseResult) -> None:
        try:
            self._send_json({
                "ok": True,
                "tasks": tasks_mod.list_tasks(include_archived=False),
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_tasks_create(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        try:
            task = tasks_mod.create(
                title=(body.get("title") or "").strip(),
                repo_path=(body.get("repo_path") or "").strip(),
                agent=(body.get("agent") or "").strip() or None,
                worktree_path=(body.get("worktree_path") or "").strip(),
                branch=(body.get("branch") or "").strip(),
            )
            self._send_json({"ok": True, "task": task})
        except TBError as e:
            self._send_tb_error(e)

    def _h_tasks_update(self, _parsed: ParseResult, body: dict) -> None:
        if not self._check_unlock():
            return
        task_id = (body.get("id") or "").strip()
        if not task_id:
            self._send_json({"ok": False, "error": "missing 'id'"}, status=400)
            return
        fields = {k: v for k, v in body.items() if k != "id"}
        try:
            task = tasks_mod.update(task_id, **fields)
            self._send_json({"ok": True, "task": task})
        except TBError as e:
            self._send_tb_error(e)

    def _h_tasks_launch(self, _parsed: ParseResult, body: dict) -> None:
        task_id = (body.get("id") or "").strip()
        if not task_id:
            self._send_json({"ok": False, "error": "missing 'id'"}, status=400)
            return
        task = tasks_mod.get_task(task_id)
        if not task:
            self._send_json({"ok": False, "error": "task not found"}, status=404)
            return
        agent_name = (task.get("agent") or "").strip()
        if not agent_name:
            self._send_json({"ok": False, "error": "no agent assigned to task"}, status=400)
            return
        # Task launch shells out to ``tb agent repl ...`` — that verb is
        # contributed by the agent extension. Refuse here when it isn't
        # registered, otherwise the spawned tmux session crashes silently
        # with "tb: unknown verb agent" and the operator has nothing to
        # debug.
        ext_verbs = self.server.extension_registry.cli_verbs
        if "agent" not in ext_verbs:
            self._send_json({
                "ok": False,
                "error": ("the agent extension isn't enabled — install or "
                          "enable it from Config > Extensions before "
                          "launching agent tasks"),
            }, status=409)
            return
        cwd = task.get("worktree_path") or task.get("repo_path") or str(config.PROJECT_DIR)
        session_name = f"task-{task_id}"
        if not sessions.exists(session_name):
            cmd = " ".join([
                shlex.quote(sys.executable), "-u",
                shlex.quote(str(config.PROJECT_DIR / "tb.py")),
                "agent", "repl", shlex.quote(agent_name),
            ])
            ok, err = sessions.new_session(session_name, cwd=cwd, cmd=cmd)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
        tasks_mod.update(task_id, session=session_name)
        tls_paths = getattr(self.server, "tls_paths", None)
        bind_addr = getattr(self.server, "ttyd_bind_addr", None)
        ttyd_result = ttyd.start(session_name, tls_paths=tls_paths, bind_addr=bind_addr)
        self._send_json({
            "ok": True,
            "task_id": task_id,
            "session": session_name,
            "port": ttyd_result.get("port"),
        })

    def _h_server_restart(self, parsed: ParseResult, body: dict) -> None:
        routes_meta.h_server_restart(self, parsed, body)

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
        _touch_client(self)
        parsed = urlparse(self.path)
        handler = self._GET_ROUTES.get(parsed.path)
        if handler is None:
            # Extension routes land here — server.extension_registry is
            # populated at startup via ``extensions.load_enabled()``.
            ext_handler = self.server.extension_registry.get_routes.get(parsed.path)
            if ext_handler is not None:
                ext_handler(self, parsed)
                return
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        handler(self, parsed)

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth_gate():
            return
        _touch_client(self)
        parsed = urlparse(self.path)
        handler = self._POST_ROUTES.get(parsed.path)
        if handler is None:
            ext_handler = self.server.extension_registry.post_routes.get(parsed.path)
            if ext_handler is not None:
                body = self._read_json()
                ext_handler(self, parsed, body)
                return
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
        "/api/sessions":           _h_sessions,
        "/api/ports":              _h_ports,
        "/api/dashboard-config":   _h_dashboard_config_get,
        "/api/session/log":        _h_session_log,
        "/api/clients":            _h_clients,
        "/api/clients/inbox":      _h_clients_inbox,
        "/api/config-lock":        _h_config_lock_status,
        "/api/extensions":         _h_extensions_status,
        "/api/extensions/available": _h_extensions_available,
        "/api/tasks":              _h_tasks_get,
        "/health":                 _h_health,
    })
    _POST_ROUTES: MappingProxyType[str, Callable[["Handler", ParseResult, dict], None]] = MappingProxyType({
        "/api/ttyd/start":         _h_ttyd_start,
        "/api/ttyd/raw":           _h_ttyd_raw,
        "/api/ttyd/stop":          _h_ttyd_stop,
        "/api/session/new":        _h_session_new,
        "/api/session/resize":     _h_session_resize,
        "/api/session/scroll":     _h_session_scroll,
        "/api/session/zoom":       _h_session_zoom,
        "/api/session/type":       _h_session_type,
        "/api/session/key":        _h_session_key,
        "/api/dashboard-config":   _h_dashboard_config_post,
        "/api/clients/nickname":   _h_clients_nickname,
        "/api/clients/send-config": _h_clients_send_config,
        "/api/config-lock":        _h_config_lock_set,
        "/api/extensions/install":   _h_extensions_install,
        "/api/extensions/uninstall": _h_extensions_uninstall,
        "/api/extensions/update":    _h_extensions_update,
        "/api/extensions/enable":    _h_extensions_enable,
        "/api/extensions/disable":   _h_extensions_disable,
        "/api/config-lock/verify": _h_config_lock_verify,
        "/api/tasks":              _h_tasks_create,
        "/api/tasks/update":       _h_tasks_update,
        "/api/tasks/launch":       _h_tasks_launch,
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

    # Load optional extensions. A failing extension is logged and
    # skipped; a route / verb / slot collision with core is fatal.
    # Post-split, extensions are opt-in: ``~/.tmux-browse/extensions.json``
    # is only written when the operator clicks Enable in the Config pane.
    core_get = set(Handler._GET_ROUTES)
    core_post = set(Handler._POST_ROUTES)
    try:
        httpd.extension_registry = extensions.load_enabled(
            core_get_routes=core_get,
            core_post_routes=core_post,
        )
    except RegistryConflict as e:
        print(f"  extensions: FATAL — {e}")
        raise
    loaded_names = sorted(
        e["name"] for e in extensions.status()
        if e["enabled"] and e["installed"] and not e["last_error"]
    )
    if loaded_names:
        print(f"  extensions: loaded {', '.join(loaded_names)}")
    else:
        print("  extensions: none enabled")
    for name, fn in httpd.extension_registry.startup:
        try:
            fn(httpd)
        except Exception as exc:  # noqa: broad — per-extension isolation
            extensions.record_error(name, f"startup failed: {exc}")

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
        for name, fn in httpd.extension_registry.shutdown:
            try:
                fn()
            except Exception as exc:  # noqa: broad — per-extension isolation
                extensions.record_error(name, f"shutdown failed: {exc}")
        httpd.shutdown()             # unblocks serve_forever()
        server_thread.join(timeout=5)
        _clear_dashboard_state()
        httpd.server_close()
