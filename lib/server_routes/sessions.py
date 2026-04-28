"""HTTP route handlers for tmux session lifecycle and I/O:
``/api/sessions``, ``/api/session/log``, ``/api/session/new``,
``/api/session/kill``, ``/api/session/resize``,
``/api/session/scroll``, ``/api/session/zoom``,
``/api/session/type``, ``/api/session/key``.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, parse_qs

from .. import config, sessions, ttyd
from ..targeting import Target

if TYPE_CHECKING:
    from ..server import Handler


def _resolve_launch_cmd(cmd: str | None) -> str | None:
    if not cmd:
        return None
    if cmd == "sysmon":
        return f"bash {config.PROJECT_DIR / 'bin' / 'sysmon.sh'}"
    if cmd == "systop":
        for tool in ("glances", "htop", "btop", "top"):
            if shutil.which(tool):
                return tool
        return (f"echo 'No top/htop/glances found. "
                f"Install: apt install htop glances'; "
                f"bash {config.PROJECT_DIR / 'bin' / 'sysmon.sh'}")
    return cmd


def h_sessions(handler: "Handler", parsed: ParseResult) -> None:
    # Lazy import — _session_summary lives in lib.server alongside its
    # dataclass so the SessionSummary type stays colocated with its
    # producer. Importing at module load would create a cycle.
    from ..server import _session_summary
    # Peer-originated requests pass ?local=1 to suppress this node's
    # own federation merge, breaking the recursive aggregation cascade.
    query = parse_qs(parsed.query)
    local_only = (query.get("local", ["0"])[0] or "0").strip().lower() in ("1", "true", "yes")
    summary = _session_summary(merge_peers=not local_only)
    handler._send_json({
        "ok": True,
        "sessions": summary.rows,
        "tmux_unreachable": summary.tmux_unreachable,
    })


def h_session_log(handler: "Handler", parsed: ParseResult) -> None:
    from ..server import _log_html, _log_error_html
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
        handler._send_text("missing 'session' query parameter", status=400)
        return
    ok, content = sessions.capture_target(Target(session=name), lines=lines)
    if not ok:
        if as_html:
            handler._send_html(_log_error_html(name, content), status=404)
        else:
            handler._send_text(content, status=404)
        return
    if as_html:
        handler._send_html(_log_html(name, content))
        return
    handler._send_text(content)


def h_session_new(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("name") or "").strip()
    cmd = _resolve_launch_cmd((body.get("cmd") or "").strip() or None)
    cwd = (body.get("cwd") or "").strip() or None
    ok, err = sessions.new_session(name, cwd=cwd, cmd=cmd)
    if not ok:
        handler._send_json({"ok": False, "error": err}, status=400)
        return
    # Auto-start ttyd if requested
    if body.get("launch_ttyd"):
        tls_paths = getattr(handler.server, "tls_paths", None)
        bind_addr = getattr(handler.server, "ttyd_bind_addr", None)
        ttyd_result = ttyd.start(name, tls_paths=tls_paths, bind_addr=bind_addr)
        handler._send_json({"ok": True, "name": name,
                            "port": ttyd_result.get("port"),
                            "url": ttyd_result.get("url", "")})
        return
    handler._send_json({"ok": True, "name": name})


def h_session_kill(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    # Stop ttyd first so the wrapper exits cleanly, then kill tmux.
    ttyd.stop(name)
    ok, err = sessions.kill(name)
    if not ok:
        handler._send_json({"ok": False, "error": err}, status=400)
        return
    handler._send_json({"ok": True})


def h_session_resize(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    cols = int(body.get("cols") or 0)
    # ``rows`` is optional — old callers only sent ``cols`` and got a
    # window-width-only resize; the new fit-to-iframe button on the
    # dashboard sends both so the terminal actually fills its
    # container vertically too.
    rows = int(body.get("rows") or 0)
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    if cols < 20 or cols > 500:
        handler._send_json({"ok": False, "error": "cols must be 20-500"}, status=400)
        return
    if rows and (rows < 5 or rows > 200):
        handler._send_json({"ok": False, "error": "rows must be 5-200"}, status=400)
        return
    argv = ["tmux", "resize-window", "-t", f"={name}", "-x", str(cols)]
    if rows:
        argv += ["-y", str(rows)]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        handler._send_json({"ok": False, "error": r.stderr.strip() or "resize failed"}, status=400)
        return
    handler._send_json({"ok": True, "cols": cols, "rows": rows or None})


def h_session_scroll(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    ok, err = sessions.enter_copy_mode(name)
    if not ok:
        handler._send_json({"ok": False, "error": err}, status=400)
        return
    handler._send_json({"ok": True})


def h_session_zoom(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    ok, err = sessions.zoom_pane(name)
    if not ok:
        handler._send_json({"ok": False, "error": err}, status=400)
        return
    handler._send_json({"ok": True})


def h_session_type(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    text = body.get("text")
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    if not isinstance(text, str) or not text.strip():
        handler._send_json({"ok": False, "error": "missing 'text'"}, status=400)
        return
    ok, err = sessions.type_line(Target(session=name), text)
    if not ok:
        handler._send_json({"ok": False, "error": err}, status=400)
        return
    handler._send_json({"ok": True})


def h_session_key(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    name = (body.get("session") or "").strip()
    keys = body.get("keys")
    if not name:
        handler._send_json({"ok": False, "error": "missing 'session'"}, status=400)
        return
    if not isinstance(keys, list) or not keys:
        handler._send_json({"ok": False, "error": "missing 'keys' (list of tmux key names)"}, status=400)
        return
    ok, err = sessions.send_keys(Target(session=name), *[str(k) for k in keys])
    if not ok:
        handler._send_json({"ok": False, "error": err}, status=400)
        return
    handler._send_json({"ok": True})
