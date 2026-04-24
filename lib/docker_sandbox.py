"""Docker sandbox for ``tb agent`` execution.

A ``Sandbox`` instance owns one container, one tmux server inside that
container, and exactly one tmux session named ``sandbox`` at ``/workspace``.

Lifecycle is owned by ``run_agent()``: callers pass a sandbox spec, never a
live ``Sandbox`` instance.

Design notes:

- ``create()`` is all-or-nothing: success leaves a verified container, failure
  removes any partial container before raising.
- ``close()`` is idempotent: callable multiple times, callable on a never-
  created instance, never raises.
- ``exec_tb()`` enforces the ``sandbox:`` target contract at the boundary —
  the model can only address the container-local tmux session.
- No runtime ``apt-get`` bootstrap. Use the prebuilt
  ``tmux-browse-sandbox:latest`` image (see ``Dockerfile.sandbox``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import StateError, UsageError


SUPPORTED: bool = shutil.which("docker") is not None

DEFAULT_IMAGE = "tmux-browse-sandbox:latest"
SESSION_NAME = "sandbox"
WORKSPACE_PATH = "/workspace"
TB_PATH_IN_CONTAINER = "/opt/tmux-browse"

# Mounts that would defeat the sandbox. Checked against resolved absolute
# paths; tests reference this constant directly.
BLOCKED_MOUNT_PATHS: frozenset[str] = frozenset({
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/etc",
    "/proc",
    "/sys",
})

# Subpaths under any user home that must never be mounted.
BLOCKED_HOME_SUBPATHS: frozenset[str] = frozenset({
    ".ssh", ".gnupg", ".aws", ".azure",
})

_NAME_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")
_DOCKER_NAME_MAX = 63  # Docker's max container name length


@dataclass
class ToolResult:
    """Mirror of ``agent_runner.ToolResult`` to avoid a circular import."""
    ok: bool
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    json_data: Any = None


def sanitize_container_name(agent_name: str, run_id: str) -> str:
    """Build a Docker-safe container name from agent + run_id."""
    raw = f"tb-sandbox-{agent_name}-{run_id}"
    cleaned = _NAME_SAFE.sub("-", raw).strip("-.")
    if not cleaned:
        raise UsageError("cannot derive a container name from agent/run_id")
    if not re.match(r"[A-Za-z0-9_.-]", cleaned[0] or ""):
        cleaned = "tb-" + cleaned
    return cleaned[:_DOCKER_NAME_MAX]


def validate_mount(host_path: Path) -> None:
    """Raise ``UsageError`` if ``host_path`` is on the mount blocklist."""
    try:
        resolved = host_path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise UsageError(f"cannot resolve mount path {host_path}: {e}")
    abs_str = str(resolved)
    if abs_str in BLOCKED_MOUNT_PATHS:
        raise UsageError(f"mount path {abs_str!r} is blocked")
    for blocked in BLOCKED_MOUNT_PATHS:
        if abs_str == blocked or abs_str.startswith(blocked + "/"):
            raise UsageError(f"mount path {abs_str!r} is blocked (under {blocked})")
    home = str(Path.home().resolve())
    if abs_str.startswith(home + "/"):
        rel = abs_str[len(home) + 1:].split("/", 1)[0]
        if rel in BLOCKED_HOME_SUBPATHS:
            raise UsageError(f"mount path {abs_str!r} is blocked (sensitive home subdir)")


def _first_positional(args: list[str]) -> str | None:
    """Return the first non-flag arg after the verb, or None.

    Used to extract the target a ``tb`` verb is acting on. Stops at ``--``.
    """
    if len(args) < 2:
        return None
    for token in args[1:]:
        if token == "--":
            return None
        if token.startswith("-"):
            continue
        return token
    return None


def _target_is_sandbox_compatible(target: str) -> bool:
    """True if ``target`` only references the ``sandbox`` session.

    Accepts: ``sandbox``, ``sandbox:``, ``sandbox:<window>``, ``sandbox.<pane>``,
    ``sandbox:<window>.<pane>``. Rejects anything addressing a different
    session name.
    """
    if not target:
        return True
    head = target.split(":", 1)[0].split(".", 1)[0]
    return head == SESSION_NAME


class Sandbox:
    """One-shot Docker container with a single tmux ``sandbox`` session."""

    def __init__(
        self,
        *,
        agent_name: str,
        run_id: str,
        workspace: Path,
        image: str = DEFAULT_IMAGE,
        repo_root: Path | None = None,
    ) -> None:
        self._agent_name = agent_name
        self._run_id = run_id
        self._workspace = Path(workspace)
        self._image = image
        # repo_root is the host path to the tmux-browse checkout that gets
        # mounted read-only at /opt/tmux-browse so tb.py is reachable.
        from . import config
        self._repo_root = Path(repo_root) if repo_root else config.PROJECT_DIR
        self._container_name = sanitize_container_name(agent_name, run_id)
        self._created = False
        self._closed = False

    @property
    def session_name(self) -> str:
        return SESSION_NAME

    @property
    def container_name(self) -> str:
        return self._container_name

    def create(self) -> None:
        """Start container, start tmux session, verify. All-or-nothing."""
        if not SUPPORTED:
            raise StateError("docker executable not found on PATH")

        validate_mount(self._workspace)
        validate_mount(self._repo_root)

        run_cmd = self._build_run_command()
        proc = subprocess.run(run_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            self._force_remove()
            raise StateError(
                f"docker run failed: {(proc.stderr or proc.stdout or '').strip()}"
            )

        try:
            self._verify_container_running()
            self._start_tmux_session()
            self._verify_tmux_session()
        except Exception:
            self._force_remove()
            raise

        self._created = True

    def close(self) -> None:
        """Idempotent teardown. No-op if never created or already closed."""
        if self._closed:
            return
        self._closed = True
        if not self._created:
            # nothing to remove; create() failed or was never called
            return
        self._force_remove()

    def exec_tb(
        self,
        args: list[str],
        stdin_text: str | None,
        timeout: int = 60,
    ) -> ToolResult:
        """Run ``tb.py`` inside the container, enforcing target isolation."""
        if not self._created or self._closed:
            raise StateError("sandbox is not active")
        if not args:
            raise UsageError("tb_command args must not be empty")
        verb = args[0]
        if verb in {"agent", "attach", "watch"}:
            raise UsageError(f"`tb {verb}` is not allowed from tb agent")

        target = _first_positional(args)
        if target is not None and not _target_is_sandbox_compatible(target):
            cmd_repr = ["tb", *args]
            return ToolResult(
                ok=False,
                command=cmd_repr,
                exit_code=2,
                stdout="",
                stderr=(
                    f"docker sandbox: target {target!r} is not allowed; "
                    f"only the {SESSION_NAME!r} session is reachable in this mode"
                ),
                json_data=None,
            )

        docker_cmd = [
            "docker", "exec", "-i",
            "-w", WORKSPACE_PATH,
            self._container_name,
            "python3", f"{TB_PATH_IN_CONTAINER}/tb.py",
            verb, "--json", *args[1:],
        ]
        try:
            proc = subprocess.run(
                docker_cmd,
                input=stdin_text if stdin_text is not None else None,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            return ToolResult(
                ok=False,
                command=docker_cmd,
                exit_code=124,
                stdout=(e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")),
                stderr=f"timed out after {timeout}s",
                json_data=None,
            )

        parsed: Any = None
        stdout = proc.stdout or ""
        if stdout.strip():
            try:
                import json as _json
                parsed = _json.loads(stdout)
            except ValueError:
                parsed = None
        return ToolResult(
            ok=proc.returncode == 0,
            command=docker_cmd,
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=proc.stderr or "",
            json_data=parsed,
        )

    def capture(self, lines: int = 200) -> str:
        """Capture the tail of the sandbox tmux session pane."""
        if not self._created or self._closed:
            raise StateError("sandbox is not active")
        cmd = [
            "docker", "exec", self._container_name,
            "tmux", "capture-pane", "-p", "-t", f"{SESSION_NAME}:", "-S", f"-{int(lines)}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.stdout or ""

    # --- internals ---------------------------------------------------------

    def _build_run_command(self) -> list[str]:
        uid_gid = f"{os.getuid()}:{os.getgid()}"
        return [
            "docker", "run", "-d",
            "--name", self._container_name,
            "--rm",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=4096",
            "--tmpfs", "/tmp:rw,exec,nosuid,size=256m",
            "--read-only",
            "--user", uid_gid,
            "--network=none",
            "-v", f"{self._workspace}:{WORKSPACE_PATH}:rw",
            "-v", f"{self._repo_root}:{TB_PATH_IN_CONTAINER}:ro",
            "-w", WORKSPACE_PATH,
            self._image,
            "sleep", "infinity",
        ]

    def _verify_container_running(self) -> None:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", self._container_name],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or proc.stdout.strip() != "true":
            raise StateError(
                f"container {self._container_name} not running: "
                f"{(proc.stderr or proc.stdout).strip()}"
            )

    def _start_tmux_session(self) -> None:
        proc = subprocess.run(
            ["docker", "exec", self._container_name,
             "tmux", "new-session", "-d", "-s", SESSION_NAME, "-c", WORKSPACE_PATH],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise StateError(
                f"tmux new-session failed: {(proc.stderr or proc.stdout).strip()}"
            )

    def _verify_tmux_session(self) -> None:
        proc = subprocess.run(
            ["docker", "exec", self._container_name,
             "tmux", "has-session", "-t", SESSION_NAME],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise StateError(
                f"tmux has-session verification failed: "
                f"{(proc.stderr or proc.stdout).strip()}"
            )

    def _force_remove(self) -> None:
        """Best-effort container removal. Never raises."""
        try:
            subprocess.run(
                ["docker", "rm", "-f", self._container_name],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            pass
