"""Optional-extension loader.

Extensions live in ``extensions/<name>/`` under the repo root, each
with a ``manifest.json`` describing its entry points. At server start,
:func:`load_enabled` walks the enabled set (from
``~/.tmux-browse/extensions.json``), loads each extension, merges its
routes / CLI verbs / UI blocks / startup hooks into core's live
tables, and returns a :class:`MergedRegistry` the server uses to
decorate itself.

E0 ships the substrate. Install / uninstall / update are stubbed until
E3/E4. Enable / disable are already real so the integration test can
flip the bit and verify reload behaviour.

See ``~/research/tmux-browse/plans/plan_split_e0_loader.md`` for the
design rationale.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .. import __version__, config
from .loader import ExtensionLoadError, load_one
from .manifest import Manifest, ManifestError
from .registry import MergedRegistry, Registration, RegistryConflict


# Repo-local extension roots live under ``<repo>/extensions/``.
EXTENSIONS_ROOT: Path = config.PROJECT_DIR / "extensions"

# Per-install toggle file — decoupled from dashboard-config.json so
# extension state doesn't mingle with UI preferences.
ENABLED_FILE: Path = config.STATE_DIR / "extensions.json"


__all__ = [
    "ExtensionLoadError",
    "Manifest",
    "ManifestError",
    "MergedRegistry",
    "Registration",
    "RegistryConflict",
    "EXTENSIONS_ROOT",
    "ENABLED_FILE",
    "discover",
    "status",
    "load_enabled",
    "enable",
    "disable",
    "record_error",
]


def discover() -> list[Path]:
    """List every directory under ``EXTENSIONS_ROOT`` that has a
    ``manifest.json``. Order is deterministic (alphabetical)."""
    if not EXTENSIONS_ROOT.is_dir():
        return []
    return sorted(
        p for p in EXTENSIONS_ROOT.iterdir()
        if p.is_dir() and (p / "manifest.json").is_file()
    )


def _read_enabled() -> dict[str, dict[str, Any]]:
    if not ENABLED_FILE.exists():
        return {}
    try:
        raw = json.loads(ENABLED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, entry in raw.items():
        if isinstance(name, str) and isinstance(entry, dict):
            out[name] = dict(entry)
    return out


def _write_enabled(data: dict[str, dict[str, Any]]) -> None:
    config.ensure_dirs()
    ENABLED_FILE.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def status() -> list[dict[str, Any]]:
    """Return one summary dict per discovered extension.

    Keys: ``name, installed, enabled, version, path, last_error``.
    ``installed`` is True iff the extension has a readable manifest.
    ``enabled`` reflects ``extensions.json``.
    """
    enabled = _read_enabled()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in discover():
        name = path.name
        seen.add(name)
        row: dict[str, Any] = {
            "name": name,
            "installed": True,
            "enabled": bool(enabled.get(name, {}).get("enabled")),
            "path": str(path),
            "version": None,
            "last_error": enabled.get(name, {}).get("last_error"),
        }
        try:
            row["version"] = Manifest.load(path / "manifest.json").version
        except ManifestError as e:
            row["installed"] = False
            row["last_error"] = str(e)
        out.append(row)
    # Extensions recorded in ``extensions.json`` but no longer on disk
    # still surface as uninstalled so operators can tell that their
    # former state wasn't silently lost.
    for name, entry in enabled.items():
        if name in seen:
            continue
        out.append({
            "name": name,
            "installed": False,
            "enabled": bool(entry.get("enabled")),
            "path": None,
            "version": None,
            "last_error": entry.get("last_error"),
        })
    return out


def enable(name: str) -> dict[str, Any]:
    data = _read_enabled()
    entry = data.get(name, {})
    entry["enabled"] = True
    entry["enabled_ts"] = int(time.time())
    entry.pop("last_error", None)
    data[name] = entry
    _write_enabled(data)
    return entry


def disable(name: str) -> dict[str, Any]:
    data = _read_enabled()
    entry = data.get(name, {})
    entry["enabled"] = False
    entry["disabled_ts"] = int(time.time())
    data[name] = entry
    _write_enabled(data)
    return entry


def record_error(name: str, message: str) -> None:
    """Persist an error message against an extension so the Config
    pane's status card can show it without re-running the load."""
    data = _read_enabled()
    entry = data.get(name, {})
    entry["last_error"] = message
    data[name] = entry
    _write_enabled(data)


def load_enabled(
    *,
    core_get_routes: set[str] | None = None,
    core_post_routes: set[str] | None = None,
    core_cli_verbs: set[str] | None = None,
    core_version_override: str | None = None,
) -> MergedRegistry:
    """Load every enabled extension; return the merged registry.

    An extension whose load fails is silently skipped for the purposes
    of the running server (its error is written to ``extensions.json``
    so the Config pane surfaces it), but the other extensions continue
    to load. This avoids one bad extension taking down the dashboard.

    Route / verb / slot collisions with core or between extensions DO
    raise — that's an operator-visible configuration problem, not a
    run-time hiccup to paper over.
    """
    core_version = core_version_override or __version__
    enabled = _read_enabled()
    merged = MergedRegistry()
    for path in discover():
        name = path.name
        if not enabled.get(name, {}).get("enabled"):
            continue
        try:
            reg = load_one(path, core_version=core_version)
            merged.add(
                reg,
                core_get_routes=core_get_routes,
                core_post_routes=core_post_routes,
                core_cli_verbs=core_cli_verbs,
            )
        except ExtensionLoadError as e:
            record_error(name, str(e))
            continue
    return merged
