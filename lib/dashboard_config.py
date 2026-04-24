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
    "agent_max_steps": 20,
    "global_daily_token_budget": 0,
    "launch_on_expand": True,
    "default_ttyd_height_vh": 70,
    "default_ttyd_min_height_px": 200,
    "day_mode": False,
    "idle_sound": "bell",
    "show_topbar": True,
    "show_topbar_title": True,
    "show_topbar_count": True,
    "show_topbar_new_session": True,
    "show_topbar_raw_ttyd": False,
    "show_topbar_refresh": False,
    "show_topbar_restart": False,
    "show_topbar_os_restart": True,
    "show_launch_claude": False,
    "show_launch_claude_yolo": False,
    "show_launch_codex": False,
    "show_launch_codex_yolo": False,
    "show_launch_kimi": False,
    "show_launch_kimi_yolo": False,
    "show_launch_monitor": False,
    "show_launch_top": False,
    "launch_cwd": "",
    "launch_ask_name": True,
    "launch_open_tab": False,
    "show_topbar_status": False,
    "show_summary_row": True,
    "show_summary_name": True,
    "show_summary_arrow": True,
    "furl_side_by_side": True,
    "resize_row_together": True,
    "show_body_actions": False,
    "show_footer": True,
    "show_inline_messages": True,
    "show_attached_badge": False,
    "show_window_badge": False,
    "show_port_badge": False,
    "show_idle_text": True,
    "show_idle_alert_button": False,
    "show_wc_idle_icon": True,
    "show_wc_scroll_icon": True,
    "show_summary_open": False,
    "show_summary_log": False,
    "show_wc_log_icon": True,
    "show_summary_scroll": False,
    "show_summary_split": False,
    "show_summary_hide": False,
    "show_wc_hide_icon": True,
    "show_summary_reorder": False,
    "show_wc_close": True,
    "show_wc_maximize": True,
    "show_wc_minimize": False,
    "show_body_launch": True,
    "show_body_stop": True,
    "show_body_kill": True,
    "show_body_send_bar": False,
    "show_body_phone_keys": False,
    "show_body_hot_buttons": True,
    "show_hot_loop_toggles": True,
}


_BOOL_KEYS = {
    key for key, value in DEFAULTS.items() if isinstance(value, bool)
}
_INT_RANGES = {
    "refresh_seconds": (1, 300),
    "hot_loop_idle_seconds": (1, 3600),
    "agent_max_steps": (1, 1000),
    "default_ttyd_height_vh": (20, 95),
    "default_ttyd_min_height_px": (120, 900),
    "global_daily_token_budget": (0, 100_000_000),
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
    out["launch_cwd"] = str(raw.get("launch_cwd") or "").strip()
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
