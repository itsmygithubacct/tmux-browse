"""Spawn, track, and stop one ttyd process per tmux session.

Each managed ttyd is identified by a PID file at ``$STATE_DIR/pids/<session>.pid``.
A log per session lives at ``$STATE_DIR/logs/<session>.log``.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.parse
from pathlib import Path

from . import config, ports


def _pidfile(session: str) -> Path:
    return config.PID_DIR / f"{_safe(session)}.pid"


def _schemefile(session: str) -> Path:
    return config.PID_DIR / f"{_safe(session)}.scheme"


def _logfile(session: str) -> Path:
    return config.LOG_DIR / f"{_safe(session)}.log"


def _safe(name: str) -> str:
    """Reversible, collision-free filename for a session name.

    Percent-encodes every non-[A-Za-z0-9_-] byte; two distinct names can
    never produce the same basename (unlike the old "replace-with-_"
    scheme, which collided ``foo bar`` with ``foo_bar``).
    """
    return urllib.parse.quote(name, safe="-_")


def _unsafe(name: str) -> str:
    """Decode a pid/log basename back to the original session name."""
    return urllib.parse.unquote(name)


def _pid_is_ttyd(pid: int) -> bool:
    """On Linux, confirm the process name is actually ``ttyd`` — guards
    against a recycled PID being mistaken for our old ttyd process."""
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip() == "ttyd"
    except OSError:
        # Non-Linux (no /proc) or pid gone — fall back to "signal 0 alive"
        # check; callers already treat _pid_alive as best-effort.
        return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # If /proc exists and the comm disagrees, the PID was recycled.
    if Path("/proc").is_dir() and not _pid_is_ttyd(pid):
        return False
    return True


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def read_pid(session: str) -> int | None:
    pf = _pidfile(session)
    if not pf.is_file():
        return None
    try:
        pid = int(pf.read_text().strip())
    except (ValueError, OSError):
        return None
    if not _pid_alive(pid):
        pf.unlink(missing_ok=True)
        _schemefile(session).unlink(missing_ok=True)
        return None
    return pid


def read_scheme(session: str) -> str:
    """Return ``"https"`` or ``"http"`` for the session's currently running
    ttyd. Defaults to ``"http"`` when no sidecar exists (e.g. started by an
    older version, or never started)."""
    sf = _schemefile(session)
    if not sf.is_file():
        return "http"
    try:
        v = sf.read_text().strip()
    except OSError:
        return "http"
    return "https" if v == "https" else "http"


def is_running(session: str) -> bool:
    port = ports.get(session)
    if port is None:
        return read_pid(session) is not None
    # Prefer the cheap pid check; fall back to port probe if no pidfile.
    if read_pid(session) is not None:
        return True
    return _port_listening(port)


def start(session: str,
          tls_paths: tuple[Path, Path] | None = None) -> dict:
    """Ensure a ttyd instance is running for ``session``. Idempotent.

    When ``tls_paths`` is set, ttyd is spawned with ``--ssl --ssl-cert --ssl-key``
    so the dashboard (which is also serving HTTPS) can embed it without
    tripping browser mixed-content blocking on the iframe's ``ws://``.
    """
    config.ensure_dirs()

    existing_pid = read_pid(session)
    port = ports.assign(session)
    if existing_pid is not None:
        return {"ok": True, "pid": existing_pid, "port": port, "already": True,
                "scheme": read_scheme(session)}

    if _port_listening(port):
        # Someone else grabbed the port (e.g. ttyd left over from a previous
        # run without a pidfile). Don't stomp it.
        return {"ok": True, "port": port, "already": True, "note": "port already in use"}

    ttyd = config.ttyd_executable()
    wrap = str(config.TTYD_WRAP)
    if not Path(wrap).is_file():
        return {"ok": False, "error": f"wrapper missing: {wrap}"}

    argv = [ttyd, "-p", str(port)]
    if tls_paths is not None:
        cert, key = tls_paths
        argv += ["--ssl", "--ssl-cert", str(cert), "--ssl-key", str(key)]
    argv += ["-W", "bash", wrap, session]

    log = _logfile(session)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab", buffering=0) as lf:
        try:
            proc = subprocess.Popen(
                argv,
                stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": (
                    "ttyd binary not found. Install it with `tmux-browse install-ttyd` "
                    "or place a ttyd executable on $PATH."
                ),
            }
        except Exception as e:
            return {"ok": False, "error": f"spawn failed: {e}"}

    _pidfile(session).write_text(f"{proc.pid}\n")
    scheme = "https" if tls_paths is not None else "http"
    _schemefile(session).write_text(f"{scheme}\n")

    # Give ttyd a moment to bind, then verify.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if _port_listening(port):
            return {"ok": True, "pid": proc.pid, "port": port, "already": False,
                    "scheme": scheme}
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": f"ttyd exited immediately (rc={proc.returncode}); see {log}",
            }
        time.sleep(0.05)
    return {"ok": True, "pid": proc.pid, "port": port, "already": False,
            "scheme": scheme, "note": "spawned but not yet listening"}


def stop(session: str) -> dict:
    pid = read_pid(session)
    if pid is None:
        _pidfile(session).unlink(missing_ok=True)
        _schemefile(session).unlink(missing_ok=True)
        return {"ok": True, "already_stopped": True}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        _pidfile(session).unlink(missing_ok=True)
        _schemefile(session).unlink(missing_ok=True)
        return {"ok": False, "error": f"kill failed: {e}"}
    # Wait briefly; escalate to SIGKILL if needed.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not _pid_alive(pid):
            break
        time.sleep(0.05)
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    _pidfile(session).unlink(missing_ok=True)
    _schemefile(session).unlink(missing_ok=True)
    return {"ok": True, "pid": pid}


def stop_all() -> int:
    killed = 0
    for pf in config.PID_DIR.glob("*.pid"):
        session = _unsafe(pf.stem)
        if stop(session).get("ok"):
            killed += 1
    return killed


def status_all() -> list[dict]:
    """Return [{session, port, pid, running}] for every known assignment + pidfile."""
    out: list[dict] = []
    seen: set[str] = set()
    for session, port in ports.all_assignments().items():
        seen.add(session)
        pid = read_pid(session)
        out.append({
            "session": session,
            "port": port,
            "pid": pid,
            "running": pid is not None,
        })
    # Orphan pidfiles without a port assignment (shouldn't happen, but surface it)
    for pf in config.PID_DIR.glob("*.pid"):
        session = _unsafe(pf.stem)
        if session not in seen:
            pid = read_pid(session)
            out.append({
                "session": session,
                "port": None,
                "pid": pid,
                "running": pid is not None,
            })
    out.sort(key=lambda r: r["session"])
    return out
