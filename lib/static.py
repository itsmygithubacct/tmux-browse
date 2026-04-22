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
JS: str = _load("app.js")
FAVICON_SVG: str = _load("favicon.svg")
