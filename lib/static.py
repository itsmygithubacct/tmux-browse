"""Dashboard CSS + JS bundles loaded from ``static/`` at import time.

Stdlib-only constraint means we don't ship a build pipeline; the assets
live as real ``.css`` / ``.js`` files in the repo's ``static/`` directory
so editors render them with the right syntax highlighting, and
``templates.py`` gets a pair of Python strings it can inline into
``<style>`` / ``<script>`` blocks.

Assets are read once at import. The dashboard server is a long-lived
process — re-reading per request would buy nothing and make the hot path
touch disk. If an asset file changes, restart via ``/api/server/restart``
(or ``systemctl restart tmux-browse``) to pick it up.
"""

from __future__ import annotations

from pathlib import Path

from .errors import StateError

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _load(name: str) -> str:
    path = _STATIC_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise StateError(
            f"missing dashboard asset {path}: {e.strerror or e} — "
            "is the ``static/`` directory alongside ``lib/``?"
        )


CSS: str = _load("app.css")

_JS_FILES = [
    "util.js",
    "state.js",
    "config.js",
    "audio.js",
    "agents.js",
    "tasks.js",
    "runs.js",
    "phone-keys.js",
    "sharing.js",
    "panes.js",
]

# One init footer sits between core JS and extension JS so extensions
# can register init callbacks without racing the core bootstrap.
_EXT_INIT_FOOTER = "window.__tbExtensions = window.__tbExtensions || [];"

# Core-only bundle; extensions layer on top via :func:`build_js`.
JS: str = "\n".join(_load(f) for f in _JS_FILES)


def build_js(extension_js: list[Path] | None = None) -> str:
    """Return the concatenated client bundle.

    Core JS first, then the ``window.__tbExtensions`` footer, then each
    extension's static JS file contents in the order given. Extension
    code sees core globals by the time it runs.
    """
    if not extension_js:
        return JS
    ext_blobs: list[str] = []
    for p in extension_js:
        try:
            ext_blobs.append(p.read_text(encoding="utf-8"))
        except OSError:
            # Missing JS file is skipped rather than fatal — the
            # extension's manifest said it had one but the disk
            # disagrees. Don't take down the dashboard over it.
            continue
    return JS + "\n" + _EXT_INIT_FOOTER + "\n" + "\n".join(ext_blobs)


FAVICON_SVG: str = _load("favicon.svg")
