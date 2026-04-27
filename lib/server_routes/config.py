"""HTTP route handlers for dashboard config + config-lock endpoints:
``/api/dashboard-config`` (GET / POST), ``/api/config-lock`` (GET / POST),
``/api/config-lock/verify``.

Lock-token state (``_unlock_tokens``, ``_UNLOCK_TOKEN_TTL_SEC``,
``_issue_unlock_token``, ``_unlock_token_valid``, ``_lock_is_active``)
stays in :mod:`lib.server` because ``Handler._check_unlock`` consumes
those helpers on every gated request, not just inside these handlers.
Imports are lazy to keep the load-time dependency one-way.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import config as conf, dashboard_config

if TYPE_CHECKING:
    from ..server import Handler


def h_dashboard_config_get(handler: "Handler", _parsed: ParseResult) -> None:
    handler._send_json({
        "ok": True,
        "config": dashboard_config.load(),
        "path": str(conf.DASHBOARD_CONFIG_FILE),
    })


def h_dashboard_config_post(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    if not handler._check_unlock():
        return
    payload = body.get("config", body)
    saved = dashboard_config.save(payload)
    handler._send_json({
        "ok": True,
        "config": saved,
        "path": str(conf.DASHBOARD_CONFIG_FILE),
    })


def h_config_lock_status(handler: "Handler", _parsed: ParseResult) -> None:
    has_lock = (conf.CONFIG_LOCK_FILE.exists()
                and conf.CONFIG_LOCK_FILE.read_text(encoding="utf-8").strip())
    handler._send_json({"ok": True, "locked": bool(has_lock)})


def h_config_lock_set(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _unlock_tokens
    # Setting or clearing the lock must itself be gated when a lock is
    # already active — otherwise anyone on the LAN could wipe it.
    if not handler._check_unlock():
        return
    password = (body.get("password") or "").strip()
    if not password:
        # Clear the lock
        try:
            conf.CONFIG_LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        # Drop every issued token on clear so they can't be reused.
        _unlock_tokens.clear()
        handler._send_json({"ok": True, "locked": False})
        return
    hashed = hashlib.sha256(password.encode("utf-8")).hexdigest()
    conf.ensure_dirs()
    conf.CONFIG_LOCK_FILE.write_text(hashed + "\n", encoding="utf-8")
    try:
        conf.CONFIG_LOCK_FILE.chmod(0o600)
    except OSError:
        pass
    handler._send_json({"ok": True, "locked": True})


def h_config_lock_verify(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _issue_unlock_token, _UNLOCK_TOKEN_TTL_SEC
    password = (body.get("password") or "").strip()
    if not conf.CONFIG_LOCK_FILE.exists():
        handler._send_json({"ok": True, "unlocked": True})
        return
    stored = conf.CONFIG_LOCK_FILE.read_text(encoding="utf-8").strip()
    if not stored:
        handler._send_json({"ok": True, "unlocked": True})
        return
    attempt = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if hmac.compare_digest(stored, attempt):
        token = _issue_unlock_token()
        handler._send_json({
            "ok": True, "unlocked": True,
            "unlock_token": token,
            "ttl_seconds": _UNLOCK_TOKEN_TTL_SEC,
        })
    else:
        handler._send_json({"ok": False, "error": "wrong password"}, status=403)
