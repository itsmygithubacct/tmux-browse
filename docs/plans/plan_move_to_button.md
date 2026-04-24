# Plan: "Move to" button for pane-group assignment

Date: 2026-04-24
Status: Proposed
Depends on: `plan_pane_groups.md`

## Problem

Once user-defined pane groups exist, the user needs a way to move a
pane between them from the summary row. Using Config every time would
be tedious.

## Goal

A "Move to" control in each pane's summary actions that opens a small
popover listing every group; clicking a group name reassigns the pane
and re-renders.

## Design

### UI surface

Two variants, governed by the same config flags as the existing
Hide/Log buttons:

- `summary-move` — a text button labeled **Move** (blue).
- `wc-move-icon` — an icon button (SVG showing an arrow pointing
  into a folder).

Both live next to the existing Hide button. Both open the same popover.

### Popover

A small `<div class="move-menu">` anchored below the button:

```
  ┌───────────────────────────┐
  │ Move "claude_code" to:    │
  │ ─────────────────────────  │
  │ ▸ Visible      (current)   │
  │   Agents                   │
  │   Monitoring               │
  │   Hidden                   │
  │ ─────────────────────────  │
  │ + New group…               │
  └───────────────────────────┘
```

Click outside or Escape closes it. Click a group → update
`state.groups.membership[session] = groupName`, save, re-render.
`+ New group` prompts for a name, creates it, then moves the pane
there in one step.

### State mutations

Single function in `static/panes.js`:

```js
function moveSessionToGroup(sessionName, groupName) {
    if (!state.groups.defs[groupName] && groupName !== "Visible" && groupName !== "Hidden") return;
    state.groups.membership[sessionName] = groupName;
    if (groupName === "Visible") delete state.groups.membership[sessionName];
    saveGroups(state.groups);
    refresh();
}
```

Edge case: "Visible" is the *absence* of a membership entry, so moving
there deletes the entry. Keeps localStorage small and avoids drift
between "no entry" and "entry pointing to Visible".

### Backwards-compat with Hide

The existing Hide button becomes a shortcut for
`moveSessionToGroup(name, "Hidden")`. Unhide = `moveSessionToGroup(name,
"Visible")`. No new state; Hide/Unhide just dispatch through the same
path. Tooltip stays the same.

### Config toggles

New flags (default `true`, parallel to the existing pattern):

- `show_summary_move` — text button
- `show_wc_move_icon` — icon button

Listed in `lib/dashboard_config.py`, `static/state.js`, and exposed in
Config > Summary Row.

### Keyboard

While a pane is focused, `m` opens its Move menu. No conflict with
existing keybindings (we have `/`, `?`, and modal dismissals; `m` is
free). Keyboard nav inside the popover is arrow keys + Enter. This is
nice-to-have; not blocking.

## Non-goals

- Multi-select "move these 5 panes to Agents". Could come later via a
  Config-pane admin control, not required here.
- Drag-and-drop between group `<details>` blocks. Drag-drop logic today
  is pane-over-pane for splits/reorder; layering on a separate group-
  drag semantic would complicate that code considerably.
- Server-side group persistence (out of scope — see pane-groups plan).

## Tests

JS only. Manual acceptance:

- Move claude_code from Visible to Agents → popover closes, pane
  disappears from Visible list, appears under Agents.
- Move claude_code from Agents to Hidden via Move menu → same effect
  as clicking Hide.
- "+ New group" from the popover: type "Staging", claude_code lands in
  Staging, Staging appears above Hidden in the group stack.
- `localStorage` contains the change on reload.

## Patch order

1. `static/panes.js` — `moveSessionToGroup` helper; refactor `toggleHidden`
   to call it.
2. `static/panes.js` — build Move button + icon + popover DOM; wire
   click handlers.
3. `lib/templates.py` — add Move toggles to Config > Summary Row; icon
   toggle in the wc-icon group.
4. `lib/dashboard_config.py` + `static/state.js` — new defaults.
5. `static/config.js` — toggle field map + visibility plumbing.
6. `static/app.css` — `.move-menu` popover styling (reuse modal-backdrop
   patterns already present).

## Acceptance criteria

- Each pane has a **Move** button (text) and icon visible (per config),
  both opening the same popover.
- Every existing group is listed; the current group is marked.
- "+ New group" works end-to-end.
- Hide / Unhide still function identically — they're now thin wrappers
  over the move path.

Estimated scope: ~2 hours riding on the pane-groups refactor being in
place.
