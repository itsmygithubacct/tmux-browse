# Plan: User-defined pane groups

Date: 2026-04-24
Status: Proposed

## Problem

Today the dashboard has exactly two "places" a pane can live:

- The main visible stack (ordered by `state.order` + `state.layout`).
- The **Hidden** furl at the bottom, toggled per pane via the Hide
  button.

Users with many panes (the author runs 13+ routinely) want more than
binary visibility: a Work bucket, an Agents bucket, a Monitoring
bucket. Today the only workaround is to Hide/Unhide in waves, which
loses ordering context and requires the whole page to scroll.

## Goal

Named groups. Each pane belongs to exactly one group. "Visible",
"Hidden" are built-in pseudo-groups; users can create arbitrary
named ones. Each group renders as its own furled `<details>` stack.

## Design

### Model

Single source of truth: `state.groups` in `localStorage`.

```js
// localStorage key: "tmux-browse:groups"
{
    // Group order (top-to-bottom render order)
    order: ["Visible", "Agents", "Monitoring", "Hidden"],

    // Group definitions. "Visible" and "Hidden" are implicit and
    // always present; user groups sit between them.
    defs: {
        "Agents":     { label: "Agents",     open: true  },
        "Monitoring": { label: "Monitoring", open: false },
    },

    // Session -> group assignment. Sessions not listed default to "Visible".
    membership: {
        "claude_code": "Agents",
        "botctl_term_gpt": "Agents",
        "servpi": "Monitoring",
    },
}
```

Invariants:

- A session can be in **one** group at a time.
- "Visible" and "Hidden" always exist; the user cannot delete them.
- "Visible" is the default bucket for any session without an explicit
  mapping — no special entry needed in `membership`.
- `state.hidden` (today's Set) becomes a derived view:
  `{name: membership[name] === "Hidden"}`. On read, keep the existing
  `state.hidden` API for backwards-compat with the rest of the code;
  it's populated from `membership`. Writes to `toggleHidden` update
  `membership` and re-derive.

### Rendering

`refresh()` currently does a single pass building one `<details>` per
session under `#sessions`. Split that into group-bucketed passes:

- For each group in `state.groups.order`:
  - Build (or reuse) a `<details class="group" data-group="Agents">`
    with summary `Agents (N)` and a per-group reorder/open state.
  - Append each session pane whose `membership[name] === groupName`
    in the existing ordered position.

The current `state.order` becomes per-group. Order key in localStorage
changes from `"tmux-browse:order"` (flat) to
`"tmux-browse:order"` (flat, legacy) + `"tmux-browse:group-order"`
(per-group).  Migration: on first load with a flat order, assign all
sessions to "Visible" with the legacy order.

### Hidden special-casing

The existing `<details id="hidden-wrap">` becomes just the "Hidden"
instance of the new group renderer. Its dedicated DOM scaffolding is
removed; one rendering path for all groups.

### Group management UI

New `<section class="config-card">` inside Config > Behavior:

```
Pane Groups
  ┌──────────────────┬─────────┬────────┐
  │ Visible          │ default │        │   (not removable)
  │ Agents           │ edit    │ remove │
  │ Monitoring       │ edit    │ remove │
  │ Hidden           │ default │        │   (not removable)
  └──────────────────┴─────────┴────────┘
  [+ New group…]
```

- `+ New group` → prompt for name, appends to `defs` and inserts above
  "Hidden" in `order`.
- `remove` → any members migrate to "Visible", group disappears.
- `edit` → rename (updates `defs` key + `membership` values atomically).

Drag-to-reorder groups (title bar drag) is a follow-up, not required
for MVP.

### Persistence and sync

- localStorage only (server remains oblivious to groups — consistent
  with how `hidden`, `order`, `layout` work today).
- QR-config share (`sharing.js`) gets `groups` added to its payload so
  a phone can import the desktop's layout.

## Non-goals

- Server-side group storage (would require a shared view, which is
  explicitly not how the existing per-browser state works).
- Cross-device sync via server.
- Nested groups / hierarchies.
- Auto-grouping heuristics (e.g. "all sessions starting with `botctl_`
  → Agents"). Could be a later feature; not in this MVP.

## Tests

Pure JS state logic — no Python tests needed, but add a minimal
Node-compatible unit-test file for `state.groups` normalization (we
don't currently have JS unit tests; skip until the project adds a
harness).

Python tests unaffected since no server code changes.

## Patch order

1. `static/state.js` — `state.groups`, normalizer, load/save helpers
   (`saveGroups`, `loadGroups`), legacy migration from `tmux-browse:hidden`.
2. `static/panes.js` — render groups instead of the flat stack; derive
   `state.hidden` from membership; update `toggleHidden` to write
   membership.
3. `lib/templates.py` — remove the dedicated `<details id="hidden-wrap">`
   and replace with a generic `<div id="sessions">` that the renderer
   fills with group-scoped `<details>` blocks.
4. `static/config.js` + templates — Pane Groups editor card in Config.
5. `static/sharing.js` — include `groups` in QR payload + import merge.
6. Docs: `docs/dashboard.md` Hidden / Groups sections collapsed into
   one "Pane Groups" description.

Ship #1-3 first as a no-op refactor (preserves today's Visible/Hidden
behavior); then #4 unlocks user-created groups. Splitting like this
keeps any regression surface tiny.

## Acceptance criteria

- Creating an "Agents" group and moving the claude_code pane into it
  renders a furled `Agents (1)` `<details>` with claude_code inside,
  and claude_code no longer appears under Visible.
- Removing the Agents group sends claude_code back to Visible with its
  order preserved.
- The existing Hide/Unhide text + icon buttons still work (they write
  to `membership` with value `"Hidden"`).
- QR share round-trips group definitions and membership.
- No regression: a fresh localStorage defaults to one "Visible" stack
  + empty "Hidden" furl (identical to today).

Estimated scope: moderate — ~4-6 hours of focused JS work plus docs.
