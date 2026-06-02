"""Install the ttyd static binary into ~/.local/bin.

Fetches the latest release asset from ``tsl0922/ttyd`` that matches the current
architecture. Stdlib-only (urllib).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import urllib.error
import urllib.request

from . import config

RELEASE_API = "https://api.github.com/repos/tsl0922/ttyd/releases/latest"
USER_AGENT = "tmux-browse-installer/1.0"

# Release assets that carry per-file SHA-256 digests, in preference order.
# ttyd publishes ``SHA256SUMS`` alongside the per-arch binaries.
_CHECKSUM_ASSET_NAMES = ("SHA256SUMS", "sha256sums.txt", "SHA256SUMS.txt")


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


def _expected_sha256(assets: list, asset_name: str) -> str | None:
    """Return the published SHA-256 for ``asset_name`` from the release's
    checksum manifest, or None if the release ships no such manifest.

    The manifest is the standard ``sha256sum`` format — one
    ``<hex>␠␠<filename>`` line per file (the filename may carry a leading
    ``*`` for binary mode). We only trust the line whose filename matches
    the asset we downloaded.
    """
    sums_url = None
    for a in assets:
        if a.get("name") in _CHECKSUM_ASSET_NAMES:
            sums_url = a.get("browser_download_url")
            break
    if sums_url is None:
        return None
    try:
        text = _http_get(sums_url).decode("utf-8", "replace")
    except urllib.error.URLError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, name = parts[0], parts[-1].lstrip("*")
        if name == asset_name and len(digest) == 64:
            return digest.lower()
    return None


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

    # Integrity check: verify the downloaded binary against the digest the
    # release publishes in its SHA256SUMS manifest. A mismatch means the
    # asset was corrupted or tampered with after it was published, so we
    # refuse to install it. If the release ships no checksum manifest we
    # proceed (HTTPS still covers transport integrity) but say so, so the
    # operator knows the digest wasn't pinned.
    actual_sha = hashlib.sha256(binary).hexdigest()
    expected_sha = _expected_sha256(meta.get("assets", []), asset_name)
    if expected_sha is not None and actual_sha != expected_sha:
        return {
            "ok": False,
            "error": (
                f"checksum mismatch for {asset_name}: release publishes "
                f"{expected_sha}, downloaded bytes hash to {actual_sha}. "
                "Refusing to install a binary that doesn't match the "
                "release manifest."
            ),
        }

    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(binary)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, target)

    return {
        "ok": True,
        "path": str(target),
        "version": tag,
        "asset": asset_name,
        "sha256": actual_sha,
        "sha256_verified": expected_sha is not None,
    }
