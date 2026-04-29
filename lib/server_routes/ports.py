"""HTTP route handler for the port registry: ``/api/ports``."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import ports

if TYPE_CHECKING:
    from ..server import Handler


def h_ports(handler: "Handler", _parsed: ParseResult) -> None:
    handler._send_json({"ok": True, "assignments": ports.all_assignments()})
