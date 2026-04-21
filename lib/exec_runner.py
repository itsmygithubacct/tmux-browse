"""``tb exec`` runner — two strategies for "run command, wait, return output".

Sentinel strategy (default for shell panes):
  Wrap the user's command in printf sentinels bracketing START/END, send it,
  then poll ``capture-pane`` until the END marker appears. Extract everything
  between the markers and parse the exit status off the END line.

Idle strategy (fallback):
  Capture the pane, send the command, poll until the capture hasn't changed
  for N seconds. Return the diff. Heuristic — "silence ≠ done" for
  long-running backgrounded work — but works anywhere.
"""

from __future__ import annotations

import re
import secrets
import time

from . import sessions
from .errors import Timeout
from .targeting import Target


_SHELL_COMMANDS = {"bash", "zsh", "fish", "sh", "dash", "ksh", "tcsh", "csh"}


def is_shell_pane(target: Target) -> bool:
    cmd = sessions.pane_current_command(target)
    return (cmd or "").lower() in _SHELL_COMMANDS


# -----------------------------------------------------------------------------
# Sentinel strategy
# -----------------------------------------------------------------------------

def exec_sentinel(target: Target, command: str,
                  timeout_sec: float = 30.0,
                  poll_sec: float = 0.2,
                  clear: bool = False,
                  interrupt_on_timeout: bool = True) -> dict:
    """Returns ``{output, exit_status, duration}``.

    ``clear``: send ``C-u`` first to drop any half-typed readline buffer.
    Recommended in LLM workflows where you can't be sure the pane was at a
    clean prompt.

    ``interrupt_on_timeout``: on timeout, send ``C-c`` to the pane so the
    command doesn't keep running in the background and corrupt subsequent
    exec runs.

    Raises ``Timeout`` if the END sentinel doesn't appear within the timeout.
    """
    tag = secrets.token_hex(6)
    start = f"__TB_{tag}_START__"
    end_re = re.compile(
        rf"^__TB_{tag}_END_(\d+)__$", re.MULTILINE,
    )
    wrapped = (
        f"printf '\\n{start}\\n'; "
        f"{command}; "
        f"__rc=$?; printf '\\n__TB_{tag}_END_%d__\\n' \"$__rc\""
    )

    if clear:
        # C-u clears from cursor to line-start; C-k from cursor to end.
        # Together they reset emacs-mode readline without side-effects
        # (bash/zsh/fish all honour them). Not sent inside type_line so
        # they're interpreted as keys, not literal characters.
        sessions.send_keys(target, "C-u", "C-k")

    t0 = time.monotonic()
    ok, err = sessions.type_line(target, wrapped)
    if not ok:
        return {"ok": False, "error": err}

    deadline = t0 + timeout_sec
    while time.monotonic() < deadline:
        ok, content = sessions.capture_target(target, lines=5000)
        if not ok:
            return {"ok": False, "error": content}
        m = end_re.search(content)
        if m:
            rc = int(m.group(1))
            duration = time.monotonic() - t0
            output = _extract(content, start, m)
            return {
                "exit_status": rc,
                "output": output,
                "duration": round(duration, 3),
                "strategy": "sentinel",
            }
        time.sleep(poll_sec)

    if interrupt_on_timeout:
        # Best-effort: send SIGINT to whatever's running in the pane so the
        # orphaned command doesn't emit its END sentinel into the *next*
        # exec call's capture window.
        sessions.send_keys(target, "C-c")
    raise Timeout(f"exec timed out after {timeout_sec}s waiting for END sentinel")


def _extract(content: str, start_marker: str, end_match: re.Match) -> str:
    """Return the text between the last START marker and the END match."""
    # The START marker may appear twice (the wrapped command line echoed
    # back + the printf's newline-prefixed emission). Use the LAST occurrence
    # before the END match to pick the genuine start of captured output.
    end_line_start = end_match.start()
    search_region = content[:end_line_start]
    idx = search_region.rfind(start_marker)
    if idx < 0:
        # Couldn't find START — return everything preceding END minus the
        # wrapped command echo line.
        return search_region.rstrip("\n")
    # Skip past the START line (marker + newline).
    after_start = idx + len(start_marker)
    if after_start < len(content) and content[after_start] == "\n":
        after_start += 1
    return content[after_start:end_line_start].rstrip("\n")


# -----------------------------------------------------------------------------
# Idle strategy
# -----------------------------------------------------------------------------

def exec_idle(target: Target, command: str,
              idle_sec: float = 2.0,
              timeout_sec: float = 30.0,
              poll_sec: float = 0.2,
              clear: bool = False,
              interrupt_on_timeout: bool = True) -> dict:
    """Send command, wait for pane to be quiet for ``idle_sec``, return diff.

    Note: ``exit_status`` is always ``null`` — silence isn't proof of
    completion. Specifically, a command backgrounded with ``&`` will show
    ``exit_status: 0`` in sentinel mode because ``$?`` after the fork is
    the shell's view of the spawn; in idle mode we return ``null`` rather
    than lie.
    """
    ok, before = sessions.capture_target(target, lines=5000)
    if not ok:
        return {"ok": False, "error": before}
    before_tail = before.rstrip("\n").split("\n")

    if clear:
        sessions.send_keys(target, "C-u", "C-k")

    t0 = time.monotonic()
    ok, err = sessions.type_line(target, command)
    if not ok:
        return {"ok": False, "error": err}

    deadline = t0 + timeout_sec
    last_hash = None
    last_change = time.monotonic()
    while True:
        ok, after = sessions.capture_target(target, lines=5000)
        if not ok:
            return {"ok": False, "error": after}
        h = hash(after)
        now = time.monotonic()
        if h != last_hash:
            last_hash = h
            last_change = now
        if now - last_change >= idle_sec:
            break
        if now >= deadline:
            if interrupt_on_timeout:
                sessions.send_keys(target, "C-c")
            raise Timeout(
                f"exec timed out after {timeout_sec}s (idle strategy)",
            )
        time.sleep(poll_sec)

    # New content = everything after the last line we saw pre-send.
    after_lines = after.rstrip("\n").split("\n")
    anchor = before_tail[-1] if before_tail else ""
    idx = -1
    if anchor:
        # Scan from the end — the anchor most likely sits near the top of
        # the newly captured text since the command scrolled output below.
        for i, line in enumerate(after_lines):
            if line == anchor:
                idx = i
    if idx >= 0:
        diff = "\n".join(after_lines[idx + 1:])
    else:
        diff = after

    return {
        "exit_status": None,  # unknown in idle mode
        "output": diff.rstrip("\n"),
        "duration": round(time.monotonic() - t0, 3),
        "strategy": "idle",
    }


# -----------------------------------------------------------------------------
# Auto-dispatch
# -----------------------------------------------------------------------------

def run(target: Target, command: str, *,
        strategy: str = "auto",
        timeout_sec: float = 30.0,
        idle_sec: float = 2.0,
        clear: bool = False,
        interrupt_on_timeout: bool = True) -> dict:
    if strategy == "auto":
        strategy = "sentinel" if is_shell_pane(target) else "idle"
    if strategy == "sentinel":
        return exec_sentinel(
            target, command,
            timeout_sec=timeout_sec, clear=clear,
            interrupt_on_timeout=interrupt_on_timeout,
        )
    if strategy == "idle":
        return exec_idle(
            target, command,
            idle_sec=idle_sec, timeout_sec=timeout_sec,
            clear=clear, interrupt_on_timeout=interrupt_on_timeout,
        )
    return {"ok": False, "error": f"unknown strategy: {strategy}"}
