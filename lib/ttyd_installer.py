"""Install the ttyd static binary into ~/.local/bin.

Fetches the latest release asset from ``tsl0922/ttyd`` that matches the current
architecture. Stdlib-only (urllib).
"""

from __future__ import annotations

import json
import os
import platform
import stat
import urllib.error
import urllib.request

from . import config

RELEASE_API = "https://api.github.com/repos/tsl0922/ttyd/releases/latest"
USER_AGENT = "tmux-browse-installer/1.0"


def _arch_asset_name() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "ttyd.x86_64"
    if machine in ("aarch64", "arm64"):
        return "ttyd.aarch64"
    if machine.startswith("armv7") or machine == "armhf":
        return "ttyd.armhf"
    if machine in ("i686", "i386"):
        return "ttyd.i686"
    raise RuntimeError(f"unsupported architecture: {machine}")


def _http_get(url: str, accept: str = "application/octet-stream") -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def install(force: bool = False) -> dict:
    target = config.TTYD_BIN
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_file() and not force:
        return {
            "ok": True,
            "path": str(target),
            "note": "already installed (use --force to reinstall)",
        }

    asset_name = _arch_asset_name()

    try:
        raw = _http_get(RELEASE_API, accept="application/vnd.github+json")
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"GitHub API unreachable: {e}"}

    meta = json.loads(raw.decode("utf-8"))
    tag = meta.get("tag_name") or "(unknown)"
    asset_url = None
    for a in meta.get("assets", []):
        if a.get("name") == asset_name:
            asset_url = a.get("browser_download_url")
            break
    if asset_url is None:
        return {
            "ok": False,
            "error": f"release {tag} has no asset named {asset_name}",
        }

    try:
        binary = _http_get(asset_url)
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"download failed: {e}"}

    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(binary)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, target)

    return {"ok": True, "path": str(target), "version": tag, "asset": asset_name}
