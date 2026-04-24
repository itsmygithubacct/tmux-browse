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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import MappingProxyType
from typing import Callable
from urllib.parse import ParseResult, parse_qs, urlparse

from . import (
    agent_budgets,
    agent_costs,
    agent_hooks,
    qr,
    agent_logs,
    agent_run_index,
    agent_scheduler,
    agent_status,
    agent_store,
    agent_runtime,
    agent_workflow_runs,
    agent_workflows,
    auth,
    tasks as tasks_mod,
    config,
    dashboard_config,
    docker_sandbox,
    ports,
    sessions,
    static,
    templates,
    tls as tls_mod,
    ttyd,
)
from .errors import TBError, UsageError
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
        self.scheduler: agent_scheduler.Scheduler | None = None


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


# --- Connected client tracking ---

_CLIENT_TIMEOUT = 60  # seconds before a client is considered gone
_clients: dict[str, dict] = {}  # keyed by client_id
_client_inbox: dict[str, list[dict]] = {}  # keyed by client_id


def _client_id(ip: str, ua: str) -> str:
    """Stable-ish fingerprint for a browser session."""
    import hashlib
    return hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:12]


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
            agents = agent_store.list_agents()
            statuses = agent_status.get_all_statuses()
            for row in agents:
                name = row.get("name", "")
                st = statuses.get(name)
                if st:
                    row["status"] = st["status"]
                    row["status_reason"] = st["reason"]
                    row["last_activity_ts"] = st["last_ts"]
                budget = agent_budgets.get_budget_status(name)
                row["budget_status"] = budget["worst_action"]
                row["budget_daily"] = budget["daily"]
            self._send_json({
                "ok": True,
                "agents": agents,
                "defaults": agent_store.catalog_rows(),
                "docker_supported": docker_sandbox.SUPPORTED,
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

    def _h_agent_workflow_state(self, _parsed: ParseResult) -> None:
        try:
            sched = getattr(self.server, "scheduler", None)
            self._send_json({
                "ok": True,
                "state": agent_workflow_runs.get_all_state(),
                "scheduler_running": sched.running if sched else False,
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_workflow_runs(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        try:
            limit = int(query.get("limit", ["50"])[0])
        except (ValueError, TypeError):
            limit = 50
        limit = max(1, min(500, limit))
        try:
            self._send_json({
                "ok": True,
                "runs": agent_workflow_runs.read_runs(limit=limit),
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_runs(self, parsed: ParseResult) -> None:
        q = parse_qs(parsed.query)

        def _first(key: str) -> str | None:
            vals = q.get(key)
            if vals:
                return vals[0].strip() or None
            return None

        def _int(key: str, default: int | None = None) -> int | None:
            v = _first(key)
            if v is None:
                return default
            try:
                return int(v)
            except ValueError:
                return default

        try:
            rows = agent_run_index.query(
                agent=_first("agent"),
                status=_first("status"),
                since=_int("since"),
                until=_int("until"),
                text=_first("q"),
                tool=_first("tool"),
                limit=max(1, min(500, _int("limit", 50) or 50)),
            )
            self._send_json({"ok": True, "runs": rows})
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_run(self, parsed: ParseResult) -> None:
        q = parse_qs(parsed.query)
        run_id = (q.get("run_id", [""])[0] or "").strip()
        if not run_id:
            self._send_json({"ok": False, "error": "missing 'run_id'"}, status=400)
            return
        row = agent_run_index.get_run(run_id)
        if row is None:
            self._send_json({"ok": False, "error": "run not found"}, status=404)
            return
        self._send_json({"ok": True, "run": row})

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
        if not name:
            self._send_json({"ok": False, "error": "missing 'session'"}, status=400)
            return
        if cols < 20 or cols > 500:
            self._send_json({"ok": False, "error": "cols must be 20-500"}, status=400)
            return
        import subprocess
        r = subprocess.run(
            ["tmux", "resize-window", "-t", f"={name}", "-x", str(cols)],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            self._send_json({"ok": False, "error": r.stderr.strip() or "resize failed"}, status=400)
            return
        self._send_json({"ok": True})

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

        def _optional_int(field: str) -> int | None:
            value = payload.get(field)
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                raise UsageError(f"{field} must be an integer")

        try:
            row = agent_store.save_agent(
                name,
                api_key=api_key,
                model=(payload.get("model") or "").strip() or None,
                base_url=(payload.get("base_url") or "").strip() or None,
                provider=(payload.get("provider") or "").strip() or None,
                wire_api=(payload.get("wire_api") or "").strip() or None,
                sandbox=(payload.get("sandbox") or "").strip() or None,
                token_budget=_optional_int("token_budget"),
                daily_token_budget=_optional_int("daily_token_budget"),
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

    def _h_agent_conversation_fork(self, _parsed: ParseResult, body: dict) -> None:
        agent_name = (body.get("name") or "").strip().lower()
        if not agent_name:
            self._send_json({"ok": False, "error": "missing 'name'"}, status=400)
            return
        try:
            new_cid = agent_runtime.fork_conversation(agent_name)
        except TBError as e:
            self._send_tb_error(e)
            return
        # Launch a new REPL session with --fork
        session_name = agent_runtime.conversation_session_name(agent_name)
        fork_session = f"{session_name}-fork"
        if not sessions.exists(fork_session):
            cmd = " ".join([
                shlex.quote(sys.executable), "-u",
                shlex.quote(str(config.PROJECT_DIR / "tb.py")),
                "agent", "repl", "--fork", shlex.quote(agent_name),
            ])
            ok, err = sessions.new_session(fork_session, cwd=str(config.PROJECT_DIR), cmd=cmd)
            if not ok:
                self._send_json({"ok": False, "error": err}, status=400)
                return
        tls_paths = getattr(self.server, "tls_paths", None)
        bind_addr = getattr(self.server, "ttyd_bind_addr", None)
        ttyd_result = ttyd.start(fork_session, tls_paths=tls_paths, bind_addr=bind_addr)
        self._send_json({
            "ok": True,
            "agent": agent_name,
            "conversation_id": new_cid,
            "session": fork_session,
            "port": ttyd_result.get("port"),
        })

    def _h_agent_hooks_get(self, _parsed: ParseResult) -> None:
        self._send_json({"ok": True, "hooks": agent_hooks.load()})

    def _h_agent_hooks_post(self, _parsed: ParseResult, body: dict) -> None:
        try:
            saved = agent_hooks.save(body.get("hooks", body))
            self._send_json({"ok": True, "hooks": saved})
        except TBError as e:
            self._send_tb_error(e)

    def _h_agent_notifications(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        try:
            limit = int(query.get("limit", ["50"])[0])
        except (ValueError, TypeError):
            limit = 50
        self._send_json({
            "ok": True,
            "notifications": agent_hooks.read_notifications(
                limit=max(1, min(200, limit))),
        })

    def _h_agent_costs(self, parsed: ParseResult) -> None:
        q = parse_qs(parsed.query)

        def _first(key: str) -> str | None:
            vals = q.get(key)
            return vals[0].strip() if vals else None

        def _int(key: str) -> int | None:
            v = _first(key)
            if v is None:
                return None
            try:
                return int(v)
            except ValueError:
                return None

        try:
            cfg = dashboard_config.load()
            self._send_json({
                "ok": True,
                "per_agent": agent_costs.per_agent_totals(
                    since=_int("since"), until=_int("until")),
                "daily": agent_costs.daily_totals(
                    since=_int("since"), until=_int("until")),
                "global_daily_budget": int(cfg.get("global_daily_token_budget") or 0),
            })
        except TBError as e:
            self._send_tb_error(e)

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

    def _h_qr(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        data = (query.get("data", [""])[0] or "").strip()
        if not data:
            self._send_json({"ok": False, "error": "missing 'data'"}, status=400)
            return
        try:
            svg = qr.generate_svg(data)
        except ValueError as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)
            return
        body = svg.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _h_config_lock_status(self, _parsed: ParseResult) -> None:
        has_lock = config.CONFIG_LOCK_FILE.exists() and config.CONFIG_LOCK_FILE.read_text(encoding="utf-8").strip()
        self._send_json({"ok": True, "locked": bool(has_lock)})

    def _h_config_lock_set(self, _parsed: ParseResult, body: dict) -> None:
        password = (body.get("password") or "").strip()
        if not password:
            # Clear the lock
            try:
                config.CONFIG_LOCK_FILE.unlink(missing_ok=True)
            except OSError:
                pass
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
            self._send_json({"ok": True, "unlocked": True})
        else:
            self._send_json({"ok": False, "error": "wrong password"}, status=403)

    def _h_tasks_get(self, _parsed: ParseResult) -> None:
        try:
            self._send_json({
                "ok": True,
                "tasks": tasks_mod.list_tasks(include_archived=False),
            })
        except TBError as e:
            self._send_tb_error(e)

    def _h_tasks_create(self, _parsed: ParseResult, body: dict) -> None:
        try:
            task = tasks_mod.create(
                title=(body.get("title") or "").strip(),
                repo_path=(body.get("repo_path") or "").strip(),
                agent=(body.get("agent") or "").strip() or None,
                branch=(body.get("branch") or "").strip() or None,
                use_worktree=body.get("use_worktree", True),
            )
            self._send_json({"ok": True, "task": task})
        except TBError as e:
            self._send_tb_error(e)

    def _h_tasks_update(self, _parsed: ParseResult, body: dict) -> None:
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
        _touch_client(self)
        parsed = urlparse(self.path)
        handler = self._GET_ROUTES.get(parsed.path)
        if handler is None:
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
        "/api/agent-workflow-state": _h_agent_workflow_state,
        "/api/agent-workflow-runs":  _h_agent_workflow_runs,
        "/api/agent-runs":           _h_agent_runs,
        "/api/agent-run":            _h_agent_run,
        "/api/session/log":        _h_session_log,
        "/api/agent-costs":        _h_agent_costs,
        "/api/agent-hooks":        _h_agent_hooks_get,
        "/api/agent-notifications": _h_agent_notifications,
        "/api/clients":            _h_clients,
        "/api/clients/inbox":      _h_clients_inbox,
        "/api/qr":                 _h_qr,
        "/api/config-lock":        _h_config_lock_status,
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
        "/api/session/type":       _h_session_type,
        "/api/session/key":        _h_session_key,
        "/api/dashboard-config":   _h_dashboard_config_post,
        "/api/agents":             _h_agents_post,
        "/api/agents/remove":      _h_agents_remove,
        "/api/agent-workflows":    _h_agent_workflows_post,
        "/api/agent-hooks":        _h_agent_hooks_post,
        "/api/agent-conversation":      _h_agent_conversation_open,
        "/api/agent-conversation-fork": _h_agent_conversation_fork,
        "/api/clients/nickname":   _h_clients_nickname,
        "/api/clients/send-config": _h_clients_send_config,
        "/api/config-lock":        _h_config_lock_set,
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

    # Start the background workflow scheduler.
    sched = agent_scheduler.Scheduler(repo_root=config.PROJECT_DIR)
    httpd.scheduler = sched
    if sched.start():
        print("  scheduler: STARTED (this process owns workflow execution)")
    else:
        print("  scheduler: passive (another process holds the lock)")

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
        sched.stop()
        httpd.shutdown()             # unblocks serve_forever()
        server_thread.join(timeout=5)
        _clear_dashboard_state()
        httpd.server_close()
