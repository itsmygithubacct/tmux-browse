# Plan: Conductor / routing layer

Date: 2026-04-24
Status: Proposed — design phase

## What's already in place

Event hooks (Phase 2, `lib/agent_hooks.py`) already dispatch configured
actions on agent lifecycle events: `run_completed`, `run_failed`,
`run_rate_limited`, `budget_exceeded`, `workflow_skipped`. Each event
fans out to a flat list of actions (`log`, `retry`, `pause_workflow`,
`notify`).

This plan is about what sits *above* that.

## What's missing — the gap

Hooks react to one event at a time. There's no way to express:

- "After three consecutive `run_failed`s from opus, pause its
  workflows for an hour, notify me, and switch its model to gpt."
- "If `claude_code` has been idle > 4h and there are pending work items
  in `~/research/`, pick one and assign it."
- "When `sonnet` hits a rate limit, retry on `opus` instead (provider
  failover), recording which agent actually completed the work."

These all require:

- **State across events** ("count consecutive failures").
- **Cross-agent routing** (one agent's failure triggers another agent's
  run, not just the same one).
- **Composite conditions** (time of day + queue depth + agent health).
- **A place that owns the decision** — distinct from the scheduler
  (which only fires due workflows) and hooks (which only fan out one
  event at a time).

Call that place a **conductor**.

## Chosen model

A conductor is a small rule engine, not a full second scheduler. It:

1. Subscribes to events emitted by `agent_hooks.execute()`.
2. Carries in-process counter / timer state keyed by (agent, event,
   rule_id).
3. When a rule's condition fires, emits an **action** that the existing
   runner / scheduler / hook layer already knows how to handle
   (run-agent, pause-workflow, notify).

The conductor does not run the LLM. It does not reimplement the agent
loop. It is a **thin policy layer** whose entire job is: receive
events, read state, decide what should happen next, and dispatch.

### Comparison with hooks

| Concern                   | Event hooks                   | Conductor                       |
|---------------------------|-------------------------------|---------------------------------|
| Triggers on               | one event                      | one or more events + conditions |
| State                      | stateless                      | in-memory + JSONL log           |
| Output                     | fixed action verbs             | same verbs, but composed         |
| Config surface             | flat list of (event, action)   | list of rules with `when` DSL    |
| Owns LLM calls             | no                             | no                               |
| Owns scheduling            | no                             | only for derived/deferred actions|

Hooks stay as-is. The conductor is a *consumer* of the same event
stream the hooks are, with a richer config language.

## Config shape

`~/.tmux-browse/agent-conductor.json`:

```json
{
    "rules": [
        {
            "id": "three-strikes-opus",
            "when": {
                "event": "run_failed",
                "agent": "opus",
                "within_last": "1h",
                "count_at_least": 3
            },
            "do": [
                {"action": "pause_workflow", "agent": "opus", "duration": "1h"},
                {"action": "notify", "message": "opus paused after 3 failures in 1h"}
            ]
        },
        {
            "id": "rate-limit-failover",
            "when": {"event": "run_rate_limited", "agent": "sonnet"},
            "do": [
                {"action": "run_agent", "agent": "opus",
                 "prompt_from": "$.original_prompt"}
            ]
        }
    ]
}
```

Keep the DSL **deliberately minimal**:

- `when.event` — string (must be one of the existing event verbs).
- `when.agent` — exact match or `"*"` for any.
- `when.within_last` + `when.count_at_least` — rolling window counter.
- `when.idle_for` — last-run-age threshold (coordinates with
  `session_logs.idle_seconds`).
- `do` — list of action dicts using **the existing hook action verbs**
  plus `run_agent` (triggers a new run with an optional prompt template).

No general predicate language, no nested booleans. If a rule needs
that, write two rules.

## Module layout

- `lib/agent_conductor.py` — new. Exposes:
  ```python
  def load_rules() -> list[Rule]
  def record_event(event: str, agent: str, context: dict) -> None
  def _eval_rules(event: str, agent: str, context: dict) -> list[Action]
  def _dispatch(action: Action) -> None
  ```
- `lib/agent_hooks.py` — call `agent_conductor.record_event(...)` at
  the same time it emits hook actions. No other changes.
- `lib/server.py` — new endpoints:
  - `GET /api/agent-conductor` → rule config
  - `POST /api/agent-conductor` → save rules (config-lock gated)
  - `GET /api/agent-conductor-events` → recent decision log
- `static/agents.js` + templates — Conductor editor card alongside
  Event Hooks in Agent Settings.

### Decision log

Every fired rule writes one JSONL line to
`~/.tmux-browse/agent-conductor.jsonl`:

```json
{"ts": 1776999999, "rule_id": "three-strikes-opus",
 "event": "run_failed", "agent": "opus", "actions": [...]}
```

This is *essential* because conductor decisions are opaque otherwise.
The decision log is append-only and surfaces via the new endpoint.

## Non-goals

- **Not a CEP engine.** No streaming windows, no complex event
  correlation.
- **Not a DAG executor.** Rules fire independently; one rule doesn't
  chain into another's condition.
- **Not persistent state.** Counters live in memory and reset on server
  restart (acceptable — most rules are windowed and re-converge).
- **No cross-host federation.** Single server instance only.

## Failure modes and guards

- **Runaway loops.** A rule whose action triggers the same event it
  listens for could loop. Guard: `_dispatch` sets a per-rule "in-flight"
  token for 5 s; re-entry within that window is dropped with a warning
  in the decision log.
- **Conflicting rules.** Two rules with `do: pause_workflow` on the
  same agent → both fire, second is a no-op (pause is idempotent).
- **Config drift.** `load_rules()` is called on every event — config
  changes take effect immediately. Rule validation rejects unknown
  `action` verbs at load time.

## Tests

`tests/test_agent_conductor.py`:

- Rule with `count_at_least: 3` only fires on the third event.
- `within_last` sliding window correctly evicts old events.
- `run_agent` action dispatches through `agent_runner.run_agent`.
- Runaway-loop guard swallows immediate re-entry.
- `*` wildcard on `when.agent` matches all agents.
- Invalid rule at load time raises a typed error; endpoint returns 400.

## Patch order

1. `lib/agent_conductor.py` — Rule parsing, event recording, rule eval,
   decision log.
2. `lib/agent_hooks.py` — one-liner call into conductor on every event.
3. `tests/test_agent_conductor.py` green.
4. `lib/server.py` — three endpoints, config-lock gated.
5. UI: new Conductor editor card in Config > Agent Settings.
6. Docs: `docs/dashboard.md` Conductor section + `CHANGELOG.md`.

## Acceptance criteria

- A `three-strikes` rule actually pauses workflows after three failures
  inside the window.
- `run_agent` action spawns a run; the result appears in the normal
  run index with `origin="conductor"`.
- Decision log grows one line per fired rule.
- Disabling the whole conductor (empty `rules` list) is indistinguishable
  from the pre-conductor behavior.

## Open questions (do not block writing; resolve before shipping)

1. Should rules be per-agent (live in the agent record) or global (one
   file)? Proposal: global for now, per-agent overrides later.
2. Should `run_agent` action support templated prompts beyond
   `$.original_prompt`? Could be a follow-up.
3. Does the conductor honor the Docker sandbox flag of the agent it
   triggers? Yes — it calls `run_agent` which already resolves
   `sandbox_spec`. Nothing special required.

Estimated scope: 1-2 full focused days. Single-file module + modest UI.
