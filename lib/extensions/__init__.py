"""Optional-extension loader.

Extensions live in ``extensions/<name>/`` under the repo root, each
with a ``manifest.json`` describing its entry points. At server start,
:func:`load_enabled` walks the enabled set (from
``~/.tmux-browse/extensions.json``), loads each extension, merges its
routes / CLI verbs / UI blocks / startup hooks into core's live
tables, and returns a :class:`MergedRegistry` the server uses to
decorate itself.

:func:`install` materialises an extension on disk (via
``git submodule update --init`` if it's already a registered submodule,
else a fresh ``git clone``) and validates its manifest. It's the
backend for the Config pane's **Download and enable** button.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__, config
from .catalog import KNOWN as CATALOG
from .loader import ExtensionLoadError, load_one
from .manifest import Manifest, ManifestError
from .registry import MergedRegistry, Registration, RegistryConflict
from . import submodule


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
    "InstallError",
    "InstallResult",
    "EXTENSIONS_ROOT",
    "ENABLED_FILE",
    "CATALOG",
    "discover",
    "status",
    "load_enabled",
    "enable",
    "disable",
    "install",
    "record_error",
]


class InstallError(RuntimeError):
    """Raised when :func:`install` can't produce a validated extension.

    ``stage`` is one of ``exists``, ``clone``, ``submodule_init``,
    ``validate``, ``unknown`` — the UI renders ``stage + msg`` so the
    operator sees the actual failure point instead of a generic
    "install failed".
    """

    def __init__(self, stage: str, msg: str):
        super().__init__(f"{stage}: {msg}")
        self.stage = stage
        self.msg = msg


@dataclass
class InstallResult:
    name: str
    version: str
    path: Path
    via: str  # "submodule" or "clone"


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


def install(name: str, spec: dict | None = None, *,
            core_version: str | None = None,
            clone_timeout: float = 120.0) -> InstallResult:
    """Fetch an extension into ``extensions/<name>/`` and validate it.

    Two paths:

    - If ``.gitmodules`` already registers ``extensions/<name>``
      (``git clone --recursive`` or a prior `git submodule add`), run
      ``git submodule update --init``. This is the fast path when the
      submodule is pinned by core.
    - Otherwise ``git clone --depth 50`` the catalog's ``repo`` into
      ``extensions/<name>/`` at ``pinned_ref``. ``--depth 50`` is
      shallow enough to clone fast but deep enough to reach a pinned
      tag or short-lived branch head.

    After either path, the fetched ``manifest.json`` is loaded and
    validated against ``core_version``. A validation failure removes
    the freshly-fetched tree so a retry starts clean.

    Raises :class:`InstallError` tagged with a ``stage`` the UI renders
    alongside the verbatim message. Does NOT flip the enabled bit —
    the caller does that so the button text and failure surface stay
    orthogonal.
    """
    spec = spec or CATALOG.get(name)
    if spec is None:
        raise InstallError("unknown", f"{name!r} is not in the catalog")
    path = EXTENSIONS_ROOT / name
    if submodule.is_submodule_path(name):
        ok, stderr = submodule.submodule_init(name, timeout=clone_timeout)
        if not ok:
            raise InstallError("submodule_init", stderr)
        via = "submodule"
    else:
        if path.exists() and any(path.iterdir()):
            raise InstallError(
                "exists",
                f"{path} already exists and is not empty — "
                "use Manage to update or uninstall first")
        path.parent.mkdir(parents=True, exist_ok=True)
        ref = spec.get("pinned_ref", "main")
        try:
            r = subprocess.run(
                ["git", "clone", "--depth", "50", "-b", ref,
                 spec["repo"], str(path)],
                capture_output=True, text=True, timeout=clone_timeout,
            )
        except subprocess.TimeoutExpired:
            _rmtree_safe(path)
            raise InstallError(
                "clone", f"git clone timed out after {clone_timeout:.0f}s")
        except FileNotFoundError:
            raise InstallError("clone", "git not on PATH")
        if r.returncode != 0:
            _rmtree_safe(path)
            raise InstallError("clone", (r.stderr or r.stdout).strip())
        via = "clone"
    manifest_path = path / "manifest.json"
    try:
        manifest = Manifest.load(manifest_path)
        manifest.validate(core_version=core_version or __version__)
    except ManifestError as e:
        _rmtree_safe(path)
        raise InstallError("validate", str(e))
    except Exception as e:
        _rmtree_safe(path)
        raise InstallError("validate", str(e))
    return InstallResult(name=name, version=manifest.version,
                         path=path, via=via)


def _rmtree_safe(path: Path) -> None:
    """Best-effort ``shutil.rmtree`` that never raises.

    Used after a failed install to leave the ``extensions/`` directory
    in a state where a retry starts clean. If rmtree itself fails (a
    submodule path we shouldn't touch, permissions, whatever) we give
    up rather than try harder — the operator will see both the original
    install error and a follow-up "partial dir exists" error next time,
    and can clean up by hand.
    """
    if not path.exists():
        return
    # Never rmtree a registered submodule path.
    if submodule.is_submodule_path(path.name):
        return
    try:
        shutil.rmtree(path)
    except OSError:
        pass
