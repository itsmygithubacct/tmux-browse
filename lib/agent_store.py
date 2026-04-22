"""Persistent agent definitions and API keys for ``tb agent``.

Stored under ``~/.tmux-browse`` with ``0600`` permissions. Keys live in a
separate file so listing agents never needs to touch secrets.
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import config
from .errors import StateError, UsageError


AGENTS_FILE = config.STATE_DIR / "agents.json"
SECRETS_FILE = config.STATE_DIR / "agent-secrets.json"
CATALOG_OVERRIDE_FILE = config.STATE_DIR / "agent-catalog.json"


SUPPORTED_WIRE_APIS = {"openai-chat", "anthropic-messages"}


# Built-in fallback. Model names in here will rot — users can override per
# agent by writing ``CATALOG_OVERRIDE_FILE`` (entries there win on name
# collision) without patching the source.
_BUILTIN_CATALOG: dict[str, dict[str, str]] = {
    "sonnet": {
        "label": "Claude Sonnet",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "base_url": "https://api.anthropic.com/v1",
        "wire_api": "anthropic-messages",
    },
    "opus": {
        "label": "Claude Opus",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "base_url": "https://api.anthropic.com/v1",
        "wire_api": "anthropic-messages",
    },
    "gpt": {
        "label": "OpenAI GPT",
        "provider": "openai",
        "model": "gpt-5.4",
        "base_url": "https://api.openai.com/v1",
        "wire_api": "openai-chat",
    },
    "kimi": {
        "label": "Moonshot Kimi",
        "provider": "moonshot",
        "model": "kimi-k2.6",
        "base_url": "https://api.moonshot.ai/v1",
        "wire_api": "openai-chat",
    },
    "minimax": {
        "label": "MiniMax",
        "provider": "minimax",
        "model": "MiniMax-M2.7",
        "base_url": "https://api.minimaxi.com/v1",
        "wire_api": "openai-chat",
    },
}


def _load_catalog_override() -> dict[str, dict[str, str]]:
    """Read the optional user catalog JSON. Silent on missing/invalid —
    overrides are supplementary, not required."""
    try:
        raw = json.loads(CATALOG_OVERRIDE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for name, spec in raw.items():
        if isinstance(name, str) and isinstance(spec, dict):
            out[name] = {
                str(k): str(v) for k, v in spec.items() if v is not None
            }
    return out


def load_catalog() -> dict[str, dict[str, str]]:
    """Return the merged catalog — user override on top of the built-in."""
    merged = dict(_BUILTIN_CATALOG)
    for name, spec in _load_catalog_override().items():
        base = dict(_BUILTIN_CATALOG.get(name, {}))
        base.update(spec)
        merged[name] = base
    return merged


# Back-compat: external code (``lib/tb_cmds/agent.py``) still reads
# ``agent_store.DEFAULT_CATALOG``. Expose the merged view under the old name;
# internal code uses ``load_catalog()`` explicitly to make the disk
# dependency visible.
def __getattr__(name: str):  # PEP 562: module-level __getattr__
    if name == "DEFAULT_CATALOG":
        return load_catalog()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _ensure_private(path) -> None:
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except OSError as e:
        raise StateError(f"cannot secure {path}: {e.strerror or e}")


def _load_json(path, *, default: Any) -> Any:
    config.ensure_dirs()
    if not path.exists():
        return default
    _ensure_private(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as e:
        raise StateError(f"cannot read {path}: {e}")
    return raw


def _save_json(path, payload: Any) -> None:
    config.ensure_dirs()
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError as e:
        raise StateError(f"cannot write {path}: {e.strerror or e}")


def _validate_name(name: str) -> str:
    out = (name or "").strip().lower()
    if not out:
        raise UsageError("agent name must be non-empty")
    if any(c.isspace() for c in out):
        raise UsageError("agent name must not contain whitespace")
    return out


def list_agents() -> list[dict[str, Any]]:
    agents = _load_json(AGENTS_FILE, default={})
    secrets = _load_json(SECRETS_FILE, default={})
    rows: list[dict[str, Any]] = []
    for name, meta in sorted(agents.items()):
        row = _normalize_agent_meta(name, meta)
        row["name"] = name
        row["has_api_key"] = bool(secrets.get(name))
        rows.append(row)
    return rows


def _normalize_agent_meta(name: str, meta: dict[str, Any]) -> dict[str, Any]:
    out = dict(meta or {})
    wire_api = (out.get("wire_api") or "").strip()
    provider = (out.get("provider") or "").strip()
    base_url = (out.get("base_url") or "").rstrip("/")
    # Older built-in Anthropic entries were stored as openai-chat; transparently
    # migrate them so existing users do not have to re-add the agent.
    if provider == "anthropic" and base_url == "https://api.anthropic.com/v1" and wire_api == "openai-chat":
        wire_api = "anthropic-messages"
    catalog = load_catalog()
    if not wire_api and name in catalog:
        wire_api = catalog[name].get("wire_api", "openai-chat")
    out["wire_api"] = wire_api or "openai-chat"
    out["base_url"] = base_url
    return out


def get_agent(name: str) -> dict[str, Any]:
    name = _validate_name(name)
    agents = _load_json(AGENTS_FILE, default={})
    secrets = _load_json(SECRETS_FILE, default={})
    meta = agents.get(name)
    if not meta:
        raise UsageError(
            f"unknown agent '{name}' — add it with `tb agent add {name} --api-key-stdin`",
        )
    api_key = (secrets.get(name) or "").strip()
    if not api_key:
        raise UsageError(f"agent '{name}' has no API key stored")
    out = _normalize_agent_meta(name, meta)
    out["name"] = name
    out["api_key"] = api_key
    return out


def add_agent(name: str, api_key: str, *,
              model: str | None = None,
              base_url: str | None = None,
              provider: str | None = None,
              wire_api: str | None = None) -> dict[str, Any]:
    name = _validate_name(name)
    key = (api_key or "").strip()
    if not key:
        raise UsageError("missing API key")
    defaults = load_catalog().get(name, {})
    entry = {
        "label": defaults.get("label", name),
        "provider": provider or defaults.get("provider", "custom"),
        "model": model or defaults.get("model"),
        "base_url": (base_url or defaults.get("base_url") or "").rstrip("/"),
        "wire_api": wire_api or defaults.get("wire_api", "openai-chat"),
    }
    if not entry["model"]:
        raise UsageError("missing model (required for custom agents)")
    if not entry["base_url"]:
        raise UsageError("missing base URL (required for custom agents)")
    if entry["wire_api"] not in SUPPORTED_WIRE_APIS:
        raise UsageError("unsupported wire API")

    agents = _load_json(AGENTS_FILE, default={})
    secrets = _load_json(SECRETS_FILE, default={})
    agents[name] = _normalize_agent_meta(name, entry)
    secrets[name] = key
    _save_json(AGENTS_FILE, agents)
    _save_json(SECRETS_FILE, secrets)
    out = dict(entry)
    out["name"] = name
    out["has_api_key"] = True
    return out


def remove_agent(name: str) -> bool:
    name = _validate_name(name)
    agents = _load_json(AGENTS_FILE, default={})
    secrets = _load_json(SECRETS_FILE, default={})
    changed = False
    if name in agents:
        del agents[name]
        changed = True
    if name in secrets:
        del secrets[name]
        changed = True
    if changed:
        _save_json(AGENTS_FILE, agents)
        _save_json(SECRETS_FILE, secrets)
    return changed
