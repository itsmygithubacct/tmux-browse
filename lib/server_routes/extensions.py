"""HTTP route handlers for the extensions surface:
``/api/extensions`` (status), ``/api/extensions/available``,
and ``/api/extensions/{install,uninstall,update,enable,disable}``.

The ``_extensions_pending_restart`` flag dict lives in
:mod:`lib.server` because the dashboard surfaces the count via
``_h_extensions_status``; routes here import it lazily so the
cycle stays one-way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import extensions

if TYPE_CHECKING:
    from ..server import Handler


def h_extensions_status(handler: "Handler", _parsed: ParseResult) -> None:
    from ..server import _extensions_pending_restart
    rows = extensions.status()
    catalog = extensions.CATALOG
    # Decorate each row with catalog metadata and submodule flag so
    # the Config pane's Extensions card has everything it needs in
    # one response (label, description, repo URL, submodule hint).
    by_name = {r["name"]: r for r in rows}
    for name, entry in catalog.items():
        row = by_name.get(name)
        if row is None:
            row = {
                "name": name,
                "installed": False,
                "enabled": False,
                "path": None,
                "version": None,
                "last_error": None,
            }
            rows.append(row)
            by_name[name] = row
        row["label"] = entry["label"]
        row["description"] = entry["description"]
        row["repo"] = entry["repo"]
        row["submodule"] = extensions.submodule.is_submodule_path(name)
        row["restart_pending"] = bool(
            _extensions_pending_restart.get(name))
    handler._send_json({"ok": True, "extensions": rows})


def h_extensions_available(handler: "Handler", _parsed: ParseResult) -> None:
    # Catalog entries rendered as a simple install-target list for
    # clients that want just "what could I install" without mingling
    # with on-disk status.
    available = [dict(v) for v in extensions.CATALOG.values()]
    handler._send_json({"ok": True, "available": available})


def h_extensions_install(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _extensions_pending_restart
    if not handler._check_unlock():
        return
    name = (body.get("name") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'name'"},
                           status=400)
        return
    if name not in extensions.CATALOG:
        handler._send_json(
            {"ok": False,
             "error": f"unknown extension {name!r}",
             "stage": "unknown"},
            status=400)
        return
    try:
        result = extensions.install(name)
    except extensions.InstallError as e:
        handler._send_json(
            {"ok": False, "error": e.msg, "stage": e.stage},
            status=500)
        return
    # Flip the enabled bit so the next restart activates the surface.
    extensions.enable(name)
    _extensions_pending_restart[name] = True
    handler._send_json({
        "ok": True,
        "name": name,
        "version": result.version,
        "via": result.via,
        "restart_required": True,
        "message": ("Installed and enabled. Restart the dashboard to "
                    "activate the extension's routes and UI."),
    })


def h_extensions_uninstall(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _extensions_pending_restart
    if not handler._check_unlock():
        return
    name = (body.get("name") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'name'"},
                           status=400)
        return
    remove_state = bool(body.get("remove_state"))
    try:
        summary = extensions.uninstall(name, remove_state=remove_state)
    except Exception as e:  # noqa: broad — surface every failure
        handler._send_json(
            {"ok": False, "error": str(e), "stage": "uninstall"},
            status=500)
        return
    _extensions_pending_restart[name] = True
    handler._send_json({
        "ok": True,
        "name": name,
        "restart_required": True,
        "summary": summary,
        "message": ("Uninstalled. Restart the dashboard to remove the "
                    "extension's routes and UI."),
    })


def h_extensions_update(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _extensions_pending_restart
    if not handler._check_unlock():
        return
    name = (body.get("name") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'name'"},
                           status=400)
        return
    try:
        result = extensions.update(name)
    except extensions.UpdateError as e:
        handler._send_json(
            {"ok": False, "error": e.msg, "stage": e.stage},
            status=500)
        return
    if result.changed:
        _extensions_pending_restart[name] = True
    handler._send_json({
        "ok": True,
        "name": name,
        "from_version": result.from_version,
        "to_version": result.to_version,
        "changed": result.changed,
        "via": result.via,
        "restart_required": result.changed,
        "message": (
            f"Updated {name} {result.from_version} → {result.to_version}. "
            "Restart the dashboard to activate."
            if result.changed else
            f"{name} is already at {result.to_version}."),
    })


def h_extensions_enable(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _extensions_pending_restart
    if not handler._check_unlock():
        return
    name = (body.get("name") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'name'"},
                           status=400)
        return
    entry = extensions.enable(name)
    _extensions_pending_restart[name] = True
    handler._send_json({
        "ok": True, "name": name, "entry": entry,
        "restart_required": True,
        "note": ("restart the dashboard to activate the extension's "
                 "routes and UI"),
    })


def h_extensions_disable(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    from ..server import _extensions_pending_restart
    if not handler._check_unlock():
        return
    name = (body.get("name") or "").strip()
    if not name:
        handler._send_json({"ok": False, "error": "missing 'name'"},
                           status=400)
        return
    entry = extensions.disable(name)
    _extensions_pending_restart[name] = True
    handler._send_json({
        "ok": True, "name": name, "entry": entry,
        "restart_required": True,
    })
