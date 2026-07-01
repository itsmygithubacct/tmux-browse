#!/usr/bin/env python3
"""Compatibility entrypoint for the tmux-browse CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    cli = here / "tmux-cli" / "tb.py"
    if not cli.is_file():
        print(f"tb.py: missing CLI submodule entrypoint: {cli}", file=sys.stderr)
        return 1
    os.execv(sys.executable, [sys.executable, str(cli), *sys.argv[1:]])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
