"""Prerequisite checks — does this host have what tmux-browse needs?

The dashboard depends on two external binaries: ``tmux`` (always) and
``ttyd`` (for the per-session web terminals). Without tmux nothing
works at all; without ttyd the session list still renders but every
expanded pane is dead. This module surfaces both conditions early
instead of letting them blow up mid-request.

A single :func:`check` call returns one :class:`Result` per dependency
with status, version, and a hint pointing at the right install path
for the host's package manager. The CLI's ``doctor`` subcommand prints
the table; ``serve`` calls the same function as a fail-fast preflight
so a fresh-clone user gets one clear error instead of a half-broken
dashboard.

Stdlib-only.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class Result:
    name: str               # "tmux", "ttyd"
    status: str             # "ok" | "missing" | "error"
    path: str | None        # resolved binary path, when found
    version: str | None     # short version string, when discoverable
    detail: str | None      # one-line context (e.g. error text)
    hint: str | None        # remediation command for the host

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _run_version(argv: list[str]) -> tuple[str | None, str | None]:
    """Best-effort ``--version`` capture. Returns (first_line, error_text)."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        return None, "binary not found"
    except subprocess.TimeoutExpired:
        return None, "version probe timed out"
    out = (r.stdout or r.stderr or "").strip().splitlines()
    return (out[0] if out else None), None


def _detect_pkg_manager() -> str | None:
    """Best-effort host-package-manager detection.

    Returns one of ``apt``/``dnf``/``yum``/``pacman``/``zypper``/``apk``/
    ``brew``/``port``/``pkg``, or ``None`` if nothing recognisable is on
    ``$PATH``. Used purely to render an install hint — we never invoke
    these directly.
    """
    if platform.system() == "Darwin":
        for tool in ("brew", "port"):
            if shutil.which(tool):
                return tool
    for tool in ("apt", "dnf", "yum", "pacman", "zypper", "apk", "pkg"):
        if shutil.which(tool):
            return tool
    return None


def _tmux_install_hint() -> str:
    pm = _detect_pkg_manager()
    cmds = {
        "apt":    "sudo apt install tmux",
        "dnf":    "sudo dnf install tmux",
        "yum":    "sudo yum install tmux",
        "pacman": "sudo pacman -S tmux",
        "zypper": "sudo zypper install tmux",
        "apk":    "sudo apk add tmux",
        "brew":   "brew install tmux",
        "port":   "sudo port install tmux",
        "pkg":    "sudo pkg install tmux",
    }
    if pm and pm in cmds:
        return cmds[pm]
    return "install tmux from your distribution's package manager"


def _ttyd_install_hint() -> str:
    pm = _detect_pkg_manager()
    if pm == "apt":
        # Some Debian/Ubuntu releases package ttyd; older ones don't.
        # The bundled installer is the reliable cross-distro path.
        return ("python3 tmux_browse.py install-ttyd  "
                "(or: sudo apt install ttyd, where packaged)")
    if pm == "brew":
        return "brew install ttyd"
    return "python3 tmux_browse.py install-ttyd"


def _check_tmux() -> Result:
    path = shutil.which("tmux")
    if not path:
        return Result(
            name="tmux",
            status="missing",
            path=None,
            version=None,
            detail="not on $PATH",
            hint=_tmux_install_hint(),
        )
    version, _ = _run_version([path, "-V"])
    return Result(
        name="tmux",
        status="ok",
        path=path,
        version=version,
        detail=None,
        hint=None,
    )


def _check_ttyd() -> Result:
    # Prefer the bundled install at ~/.local/bin/ttyd; fall back to $PATH.
    bundled = config.TTYD_BIN
    path: str | None
    if bundled.is_file() and os.access(bundled, os.X_OK):
        path = str(bundled)
    else:
        path = shutil.which("ttyd")
    if not path:
        return Result(
            name="ttyd",
            status="missing",
            path=None,
            version=None,
            detail=f"not on $PATH and no binary at {bundled}",
            hint=_ttyd_install_hint(),
        )
    version, err = _run_version([path, "--version"])
    if err and not version:
        return Result(
            name="ttyd",
            status="error",
            path=path,
            version=None,
            detail=err,
            hint=_ttyd_install_hint(),
        )
    return Result(
        name="ttyd",
        status="ok",
        path=path,
        version=version,
        detail=None,
        hint=None,
    )


def check() -> list[Result]:
    """Run every prereq check; cheap enough to call from CLI startup."""
    return [_check_tmux(), _check_ttyd()]


def required_missing(results: list[Result] | None = None) -> list[Result]:
    """Subset of :func:`check` that the dashboard cannot run without."""
    rows = results if results is not None else check()
    return [r for r in rows if r.status != "ok"]


def format_table(results: list[Result]) -> str:
    """Pretty render for the ``doctor`` subcommand."""
    name_w = max(len(r.name) for r in results)
    status_w = max(len(r.status) for r in results)
    lines = []
    for r in results:
        ver = r.version or "-"
        path = r.path or "-"
        line = f"{r.name:<{name_w}}  {r.status:<{status_w}}  {ver:<14}  {path}"
        lines.append(line)
        if r.detail:
            lines.append(f"  {' ' * (name_w + status_w)}↳ {r.detail}")
        if r.hint:
            lines.append(f"  {' ' * (name_w + status_w)}↳ install: {r.hint}")
    return "\n".join(lines)
