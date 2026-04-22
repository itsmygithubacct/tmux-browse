"""Dashboard UI config file helpers."""

from __future__ import annotations

import json
from typing import Any

from . import config


IDLE_SOUND_CHOICES: tuple[str, ...] = (
    "beep", "chime", "knock", "bell", "blip", "ding",
)


DEFAULTS: dict[str, Any] = {
    "auto_refresh": False,
    "refresh_seconds": 5,
    "hot_loop_idle_seconds": 5,
    "launch_on_expand": True,
    "default_ttyd_height_vh": 70,
    "default_ttyd_min_height_px": 200,
    "idle_sound": "beep",
    "show_topbar_status": True,
    "show_footer": True,
    "show_inline_messages": True,
    "show_attached_badge": True,
    "show_window_badge": True,
    "show_port_badge": True,
    "show_idle_text": True,
    "show_idle_alert_button": True,
    "show_summary_open": True,
    "show_summary_log": True,
    "show_summary_scroll": True,
    "show_summary_split": True,
    "show_summary_hide": True,
    "show_summary_reorder": True,
    "show_body_launch": False,
    "show_body_stop": False,
    "show_body_kill": False,
    "show_body_hot_buttons": True,
    "show_hot_loop_toggles": True,
}


_BOOL_KEYS = {
    key for key, value in DEFAULTS.items() if isinstance(value, bool)
}
_INT_RANGES = {
    "refresh_seconds": (1, 300),
    "hot_loop_idle_seconds": (1, 3600),
    "default_ttyd_height_vh": (20, 95),
    "default_ttyd_min_height_px": (120, 900),
}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _coerce_choice(value: Any, default: str, choices: tuple[str, ...]) -> str:
    if isinstance(value, str) and value in choices:
        return value
    return default


def normalize(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    out = dict(DEFAULTS)
    for key in _BOOL_KEYS:
        out[key] = _coerce_bool(raw.get(key), DEFAULTS[key])
    for key, (lo, hi) in _INT_RANGES.items():
        out[key] = _coerce_int(raw.get(key), DEFAULTS[key], lo, hi)
    out["idle_sound"] = _coerce_choice(raw.get("idle_sound"), DEFAULTS["idle_sound"], IDLE_SOUND_CHOICES)
    return out


def load() -> dict[str, Any]:
    config.ensure_dirs()
    try:
        raw = json.loads(config.DASHBOARD_CONFIG_FILE.read_text())
    except (OSError, ValueError, TypeError):
        return dict(DEFAULTS)
    return normalize(raw)


def save(raw: Any) -> dict[str, Any]:
    config.ensure_dirs()
    normalized = normalize(raw)
    config.DASHBOARD_CONFIG_FILE.write_text(
        json.dumps(normalized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized
