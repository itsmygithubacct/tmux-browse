# Plan: Server-side config-lock enforcement

Date: 2026-04-24
Status: Proposed

## Problem

The config-lock password today is purely cosmetic on the server. Proof:

- `GET /api/config-lock` — reports whether a lock exists
- `POST /api/config-lock` — sets/clears the lock
- `POST /api/config-lock/verify` — returns `ok: true` on correct password

Every other endpoint — `POST /api/agents`, `POST /api/agents/remove`,
`POST /api/agent-hooks`, `POST /api/agent-workflows`, `POST /api/dashboard-config`,
`POST /api/tasks`, etc. — writes freely regardless of the lock. A curl
against the bare endpoint bypasses the UI entirely.

This is not a theoretical concern: a phone on the LAN with auto-refresh
off can still issue mutating POSTs because the client-side lock only
gates the Config *pane's* visibility.

## Goal

A mutating request to any "configuration" endpoint either:

- succeeds when the lock is **unset**, or
- succeeds when the request presents a **valid short-lived unlock token**
  derived from the password, or
- is rejected with **403**.

Reads remain unauthenticated. Dashboard rendering, session listing,
ttyd spawn, and all GETs are unchanged — the goal is to stop silent
config mutation on a shared LAN, not to build a full auth system.

## Design

### Unlock token, not password-on-every-call

- On `POST /api/config-lock/verify` (correct password) the server
  generates a random 32-byte token, stores `(token, expiry=now+12h)` in
  an in-memory dict, and returns `{ok: true, unlock_token: "..."}`.
- Client stores it in `localStorage` under `tmux-browse:unlock-token`
  (scoped like the other client-state keys).
- Subsequent mutating requests include `X-TB-Unlock-Token: <token>` header.
- Server checks token before executing the mutation; on miss / expired
  / mismatch → 403.
- Tokens are ephemeral: cleared on server restart (forces re-unlock,
  which is acceptable for this use case). No disk persistence.

### Why not passwords-on-every-call?

- Passwords can't round-trip through ad-hoc curl / shell scripts without
  leaking to process lists and shell history.
- A short-lived token gives the browser session a clean way to hold the
  unlock without re-prompting every click.
- Token loss = re-enter password; password loss = full reset (same as
  today).

### Which endpoints are gated?

Gate every *mutation* path that writes to `~/.tmux-browse/`:

- `POST /api/agents`, `POST /api/agents/remove`
- `POST /api/agent-hooks`
- `POST /api/agent-workflows`
- `POST /api/dashboard-config`
- `POST /api/tasks`, `POST /api/tasks/update`
- `POST /api/config-lock/*` except `/verify` (setting/clearing the lock
  itself requires the current unlock token if one is set)

Do **not** gate:

- Any GET
- `POST /api/ttyd/*` (start/stop ttyd) — operational, not config
- `POST /api/session/*` (new/kill/send-keys) — operational
- `POST /api/agent-conversation*` — operational, already requires agents
  to exist (which required an unlock to add)

### Server shape

New helper in `lib/server.py`:

```python
_unlock_tokens: dict[str, int] = {}  # token -> expiry epoch
_TOKEN_TTL_SEC = 43200  # 12h

def _issue_unlock_token() -> str: ...
def _check_unlock(handler) -> bool:
    # True if no lock set OR header presents a valid token
```

A small decorator or explicit call at the top of gated handlers:

```python
if not self._check_unlock():
    self._send_json({"ok": False, "error": "config locked"}, status=403)
    return
```

### Client shape (`static/config.js`)

- Extend `setConfigLock()` / `verifyLock()` to capture the token.
- Store `state.unlockToken` + persist to `tmux-browse:unlock-token`.
- Update `api()` helper (`static/util.js`) to include the header on all
  non-GET requests when token is present.
- On 403 with `"config locked"`: clear stored token, re-open the unlock
  prompt, retry the request after unlock.

## Non-goals

- No per-user / per-role authorization.
- No audit logging (could be added later, not required here).
- No cert-pinning or cross-origin protection beyond existing Bearer auth.
- No TLS changes.

## Tests

`tests/test_config_lock.py` (new) covers:

- Unlocked host: mutations succeed without any header.
- Locked host, no header: 403.
- Locked host, wrong token: 403.
- Locked host, valid token: 200.
- Token expiry: clock-fast-forward → 403.
- `/verify` returns a fresh token; `/status` does not leak tokens.

`tests/test_server_agents.py`, `tests/test_agent_hooks.py` (etc.) extend
with a "gated when locked" assertion to prove the wiring actually
routes through `_check_unlock`.

## Patch order

1. `lib/server.py` — token store, `_check_unlock` helper, gate the
   six endpoints listed above. Add `_issue_unlock_token` to `/verify`.
2. Tests green.
3. `static/util.js` — `api()` includes the header.
4. `static/config.js` — capture + store token; retry-on-403 flow.
5. Docs: `docs/dashboard.md` Config Lock section — document the token
   model and the 12 h TTL.

## Acceptance criteria

- `curl -X POST /api/agents -d '{...}'` against a locked dashboard
  returns 403 (previously 200).
- UI on a phone that lost its stored token prompts for the password
  once and then mutating works for the 12 h window.
- No endpoint gated today (e.g., session creation) is newly gated.
- CHANGELOG entry.

Estimated scope: 1-2 focused hours.
