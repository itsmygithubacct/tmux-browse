"""HTTP route handlers for connected-browser tracking and config sharing:
``/api/clients``, ``/api/clients/nickname``, ``/api/clients/send-config``,
``/api/clients/inbox``.

The state (``_clients`` / ``_client_inbox`` dicts and the
``_touch_client`` / ``_active_clients`` helpers) lives in
:mod:`lib.server` because the dispatcher in ``do_GET`` / ``do_POST``
calls ``_touch_client`` on every request, not only inside these
handlers. Importing the helpers lazily here keeps the load-time
dependency one-way.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

if TYPE_CHECKING:
    from ..server import Handler


def h_clients(handler: "Handler", _parsed: ParseResult) -> None:
    from ..server import _touch_client, _active_clients
    my_id = _touch_client(handler)
    handler._send_json({
        "ok": True,
        "clients": _active_clients(),
        "you": my_id,
    })


def h_clients_nickname(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _touch_client, _clients
    cid = _touch_client(handler)
    nickname = (body.get("nickname") or "").strip()[:30]
    if cid in _clients:
        _clients[cid]["nickname"] = nickname
    handler._send_json({"ok": True, "client_id": cid, "nickname": nickname})


def h_clients_send_config(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _touch_client, _clients, _client_inbox
    my_id = _touch_client(handler)
    target_id = (body.get("target") or "").strip()
    config_url = (body.get("config_url") or "").strip()
    if not target_id or not config_url:
        handler._send_json({"ok": False, "error": "missing target or config_url"}, status=400)
        return
    if target_id not in _clients:
        handler._send_json({"ok": False, "error": "target client not connected"}, status=404)
        return
    inbox = _client_inbox.setdefault(target_id, [])
    sender = _clients.get(my_id, {})
    inbox.append({
        "from": sender.get("nickname") or sender.get("ip", "unknown"),
        "from_id": my_id,
        "config_url": config_url,
        "ts": int(time.time()),
    })
    # Keep inbox bounded
    if len(inbox) > 10:
        inbox[:] = inbox[-10:]
    handler._send_json({"ok": True, "sent": True})


def h_clients_inbox(handler: "Handler", _parsed: ParseResult) -> None:
    from ..server import _touch_client, _client_inbox
    cid = _touch_client(handler)
    messages = _client_inbox.pop(cid, [])
    handler._send_json({"ok": True, "messages": messages})
