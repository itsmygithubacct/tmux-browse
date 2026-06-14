"""Make ``pytest`` work the same way ``make test`` does.

The ``tb`` CLI core ships as the ``tmux-cli`` git submodule, and the
``lib`` package is a namespace package whose modules are split across
this repo's ``lib/`` and the submodule's ``lib/``. The Makefile runs the
suite with ``PYTHONPATH=tmux-cli TB_PROJECT_DIR=$(CURDIR)`` so both
halves merge; a bare ``pytest`` invocation has neither, so collection
fails with ``cannot import name 'config' from 'lib'``.

This conftest reproduces that environment for any pytest run rooted at
the repo, so contributors can use ``pytest``/``pytest -k`` directly
without remembering the env prelude. ``make test`` (unittest) is
unaffected — it already sets these.
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# Submodule first so the core ``lib`` modules are importable, then the
# repo root so the dashboard-only ``lib`` modules merge into the same
# namespace package. Mirrors the sys.path ordering in tmux_browse.py.
for _p in (_ROOT / "tmux-cli", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# config.py reads TB_PROJECT_DIR to locate bin/ assets (e.g. ttyd_wrap.sh)
# when running from inside the submodule. Default it to the repo root,
# matching the Makefile, without clobbering an explicit override.
os.environ.setdefault("TB_PROJECT_DIR", str(_ROOT))
