// Layout, ordering, drag-and-drop, hidden / pane-group bookkeeping.
//
// state.layout is a list of rows; each row is a list of session names
// rendering side-by-side. state.order is the flat fallback (used for
// hidden + new arrivals not yet placed by drag/drop). state.hidden
// is a Set of names tucked into the bottom drawer; state.groups is
// the user-defined-buckets registry. All four persist to localStorage
// via state.js.
//
// Functions here run after panes are created (render.js / createPane)
// and before/after refresh: renderLayout walks state.layout and
// arranges each rec.details element into the right row, group, or
// hidden drawer.

function visibleSessionNames() {
    // Visible = not hidden AND not in a user-defined group.
    return state.sessions.map((s) => s.name).filter((n) =>
        !state.hidden.has(n) && !state.groups.membership[n]);
}

function hiddenSessionNames() {
    return state.sessions.map((s) => s.name).filter((n) => state.hidden.has(n));
}

function sessionsInGroup(groupName) {
    return state.sessions
        .map((s) => s.name)
        .filter((n) => state.groups.membership[n] === groupName);
}

// Popover menu for the Move button. Lists all reachable buckets
// (Visible + user groups + Hidden) and an inline "New group…" option.
// Click-outside and Escape close it.
let _moveMenuOpen = null;

function openMoveMenu(sessionName, anchorEl) {
    closeMoveMenu();
    const current = state.groups.membership[sessionName]
        || (state.hidden.has(sessionName) ? "Hidden" : "Visible");
    const menu = el("div", { class: "move-menu" });
    const heading = el("div", { class: "move-menu-head" },
        `Move "${sessionName}" to:`);
    menu.append(heading);
    const rowFor = (group) => {
        const isCurrent = group === current;
        const row = el("div", {
            class: "move-menu-row" + (isCurrent ? " current" : ""),
            onclick: (e) => {
                e.preventDefault();
                e.stopPropagation();
                moveSessionToGroup(sessionName, group);
                closeMoveMenu();
            },
        }, group + (isCurrent ? "  (current)" : ""));
        return row;
    };
    menu.append(rowFor("Visible"));
    for (const g of state.groups.order) {
        if (state.groups.defs[g]) menu.append(rowFor(g));
    }
    menu.append(rowFor("Hidden"));
    menu.append(el("div", { class: "move-menu-sep" }));
    menu.append(el("div", {
        class: "move-menu-row new-group",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            const name = prompt("New group name:");
            closeMoveMenu();
            if (!name) return;
            const trimmed = name.trim();
            if (!trimmed || trimmed === "Visible" || trimmed === "Hidden") return;
            if (!state.groups.defs[trimmed]) {
                state.groups.defs[trimmed] = { label: trimmed, open: true };
                state.groups.order.push(trimmed);
                saveGroups();
            }
            moveSessionToGroup(sessionName, trimmed);
        },
    }, "+ New group…"));
    // Anchor below the clicked button.
    const rect = anchorEl.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 4}px`;
    menu.style.left = `${rect.left + window.scrollX}px`;
    document.body.append(menu);
    _moveMenuOpen = menu;
    // Delay binding the outside-click listener so the click that opened
    // the menu doesn't immediately close it.
    setTimeout(() => {
        document.addEventListener("click", closeMoveMenu, { once: true });
        document.addEventListener("keydown", _escCloseMoveMenu);
    }, 0);
}

function closeMoveMenu() {
    if (_moveMenuOpen) {
        _moveMenuOpen.remove();
        _moveMenuOpen = null;
    }
    document.removeEventListener("keydown", _escCloseMoveMenu);
}

function _escCloseMoveMenu(e) {
    if (e.key === "Escape") closeMoveMenu();
}

// Unified mover. Clears conflicting placements so a session is only in
// one place at a time (Visible / Hidden / one user group).
function moveSessionToGroup(sessionName, groupName) {
    const isUserGroup = state.groups.defs[groupName] !== undefined;
    if (groupName === "Visible") {
        state.hidden.delete(sessionName);
        delete state.groups.membership[sessionName];
    } else if (groupName === "Hidden") {
        delete state.groups.membership[sessionName];
        state.hidden.add(sessionName);
    } else if (isUserGroup) {
        state.hidden.delete(sessionName);
        state.groups.membership[sessionName] = groupName;
    } else {
        return;  // unknown group
    }
    saveHidden(state.hidden);
    saveGroups();
    refresh();
}

function flattenRows(rows) {
    return rows.flatMap((row) => Array.isArray(row) ? row : []);
}

function normalizeLayoutRows(rows, visibleNames) {
    const visible = new Set(visibleNames);
    const out = [];
    const seen = new Set();
    if (Array.isArray(rows)) {
        for (const rawRow of rows) {
            if (!Array.isArray(rawRow)) continue;
            const row = rawRow.filter((name) => visible.has(name) && !seen.has(name));
            if (!row.length) continue;
            row.forEach((name) => seen.add(name));
            out.push(row);
        }
    }
    for (const name of sortedSessionNames(visibleNames.filter((name) => !seen.has(name)))) {
        out.push([name]);
    }
    return out;
}

function syncLayoutState() {
    state.layout = normalizeLayoutRows(state.layout, visibleSessionNames());
    return state.layout;
}

function persistLayoutState() {
    syncLayoutState();
    saveLayout(state.layout);
    state.order = [...flattenRows(state.layout), ...sortedSessionNames(hiddenSessionNames())];
    saveOrder(state.order);
}

function findLayoutPosition(name) {
    for (let row = 0; row < state.layout.length; row += 1) {
        const col = state.layout[row].indexOf(name);
        if (col >= 0) return { row, col };
    }
    return null;
}

function removeFromLayout(name) {
    const pos = findLayoutPosition(name);
    if (!pos) return null;
    state.layout[pos.row].splice(pos.col, 1);
    if (!state.layout[pos.row].length) state.layout.splice(pos.row, 1);
    return pos;
}

function placeSessionRow(name, rowIndex) {
    const idx = Math.max(0, Math.min(rowIndex, state.layout.length));
    state.layout.splice(idx, 0, [name]);
}

function putSessionBeside(targetName, sessionName, side) {
    if (!sessionName || !targetName || sessionName === targetName) return;
    if (state.hidden.has(targetName)) return;
    syncLayoutState();
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    const row = state.layout[targetPos.row];
    // Cap at 4 panes side-by-side
    if (row.length >= 4 && !row.includes(sessionName)) return;
    if (state.hidden.has(sessionName)) {
        state.hidden.delete(sessionName);
        saveHidden(state.hidden);
    }
    removeFromLayout(sessionName);
    // Re-find after removal may have shifted indices
    const pos = findLayoutPosition(targetName);
    if (!pos) return;
    const targetRow = state.layout[pos.row];
    const insertAt = side === "left" ? pos.col : pos.col + 1;
    targetRow.splice(insertAt, 0, sessionName);
    persistLayoutState();
    renderLayout();
}

function placeSessionAbove(targetName, sessionName) {
    if (!sessionName || !targetName || sessionName === targetName) return;
    const sameBucket = state.hidden.has(sessionName) === state.hidden.has(targetName);
    if (!sameBucket) return;
    if (state.hidden.has(sessionName)) {
        const liveNames = state.sessions.map((s) => s.name);
        const bucket = liveNames.filter((n) => state.hidden.has(n));
        const current = sortedSessionNames(bucket).filter((n) => n !== sessionName);
        const to = current.indexOf(targetName);
        if (to < 0) return;
        current.splice(to, 0, sessionName);
        const visibleFlat = flattenRows(syncLayoutState());
        state.order = [...visibleFlat, ...current];
        saveOrder(state.order);
        renderLayout();
        return;
    }
    syncLayoutState();
    removeFromLayout(sessionName);
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    placeSessionRow(sessionName, targetPos.row);
    persistLayoutState();
    renderLayout();
}

function placeSessionBelow(targetName, sessionName) {
    if (!sessionName || !targetName || sessionName === targetName) return;
    if (state.hidden.has(sessionName) !== state.hidden.has(targetName)) return;
    if (state.hidden.has(sessionName)) return;
    syncLayoutState();
    removeFromLayout(sessionName);
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    placeSessionRow(sessionName, targetPos.row + 1);
    persistLayoutState();
    renderLayout();
}

function _makeDropBar(insertRowIdx) {
    const bar = el("div", { class: "row-drop-bar" });
    bar.addEventListener("dragover", (e) => {
        if (!e.dataTransfer.types.includes("text/x-tmux-browse-split") &&
            !e.dataTransfer.types.includes("text/x-tmux-browse-session")) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        bar.classList.add("visible");
    });
    bar.addEventListener("dragleave", () => bar.classList.remove("visible"));
    bar.addEventListener("drop", (e) => {
        const name = e.dataTransfer.getData("text/x-tmux-browse-split") ||
                     e.dataTransfer.getData("text/x-tmux-browse-session");
        bar.classList.remove("visible");
        if (!name) return;
        e.preventDefault();
        syncLayoutState();
        if (state.hidden.has(name)) {
            state.hidden.delete(name);
            saveHidden(state.hidden);
        }
        removeFromLayout(name);
        placeSessionRow(name, insertRowIdx);
        persistLayoutState();
        renderLayout();
    });
    return bar;
}

// Layout-relevant signature: anything that would change which
// rec.details element belongs in which DOM container, in what
// order. SSE refreshes feed applySessions() at ~1Hz; without this
// short-circuit, every tick clears #sessions and re-appends each
// pane's <details>, which detaches+reattaches the embedded ttyd
// iframe and forces it to reload — causing the panes to flicker
// to black on every refresh and never stabilise.
//
// Note: refreshHiddenChrome() updates the hidden-count badge based
// on the current sessions list, so we still call it on every
// invocation regardless of whether the DOM rebuild was skipped.
function _layoutSignature() {
    const liveNames = state.sessions.map((s) => s.name);
    return JSON.stringify({
        layout: state.layout,
        hidden: liveNames.filter((n) => state.hidden.has(n)),
        groupsOrder: state.groups.order,
        groupsDefs: state.groups.defs,
        membership: liveNames.reduce((acc, n) => {
            const g = state.groups.membership[n];
            if (g) acc[n] = g;
            return acc;
        }, {}),
        live: liveNames,
    });
}

function renderLayout() {
    syncLayoutState();
    const sig = _layoutSignature();
    if (sig === state._lastLayoutSig) {
        // Layout hasn't moved; skip the destructive DOM rebuild but
        // still refresh derived chrome.
        refreshHiddenChrome();
        return;
    }
    state._lastLayoutSig = sig;
    const root = document.getElementById("sessions");
    root.textContent = "";
    for (let ri = 0; ri < state.layout.length; ri++) {
        const row = state.layout[ri];
        // Drop bar before this row
        root.append(_makeDropBar(ri));
        const rowEl = el("div", { class: "session-row" });
        for (const name of row) {
            const rec = state.nodes.get(name);
            if (rec) rowEl.append(rec.details);
        }
        if (rowEl.childNodes.length) root.append(rowEl);
    }
    // Drop bar after last row
    if (state.layout.length) root.append(_makeDropBar(state.layout.length));
    if (!state.layout.length) {
        root.append(el("div", { id: "empty", class: "empty-state" },
            state.sessions.length === 0
                ? "No tmux sessions. Create one above."
                : "All sessions are hidden — open the list below."));
    }

    // User-defined pane groups render between the visible stack and the
    // Hidden drawer. Each group is its own furled <details> with its own
    // pane order derived from `state.order` but scoped to group members.
    const groupsRoot = document.getElementById("sessions-groups");
    if (groupsRoot) {
        groupsRoot.textContent = "";
        for (const groupName of state.groups.order) {
            const def = state.groups.defs[groupName];
            if (!def) continue;
            const members = sortedSessionNames(sessionsInGroup(groupName));
            const wrap = el("details", {
                id: `group-wrap-${cssId(groupName)}`,
                class: "group-wrap",
                "data-group": groupName,
            });
            if (def.open !== false || members.length) wrap.open = def.open !== false;
            const summary = el("summary", {},
                `${def.label || groupName} (${members.length})`);
            wrap.append(summary);
            const body = el("div", { class: "group-body" });
            for (const name of members) {
                const rec = state.nodes.get(name);
                if (rec) body.append(rec.details);
            }
            wrap.append(body);
            groupsRoot.append(wrap);
        }
    }

    const hiddenRoot = document.getElementById("sessions-hidden");
    hiddenRoot.textContent = "";
    for (const name of sortedSessionNames(hiddenSessionNames())) {
        const rec = state.nodes.get(name);
        if (rec) hiddenRoot.append(rec.details);
    }
    refreshHiddenChrome();
}

function sortedSessionNames(names) {
    // Honour state.order first (filtered to existing sessions in their stored
    // order), then append any unordered sessions alphabetically.
    const set = new Set(names);
    const ordered = state.order.filter(n => set.has(n));
    const seen = new Set(ordered);
    const rest = [...names].filter(n => !seen.has(n)).sort();
    return [...ordered, ...rest];
}

function placePane(rec, name) {
    const hidden = state.hidden.has(name);
    rec.hideBtn.textContent = hidden ? "Unhide" : "Hide";
    rec.hideBtn.title = hidden
        ? "unhide this session"
        : "move to the hidden list at the bottom of the page";
    if (rec.hideIconBtn) {
        rec.hideIconBtn.title = hidden ? "unhide this session" : "hide this session";
    }
}

function reappendInOrder() {
    renderLayout();
}

function moveSession(name, delta) {
    if (!state.hidden.has(name)) {
        syncLayoutState();
        const pos = findLayoutPosition(name);
        if (!pos) return;
        removeFromLayout(name);
        const insertAt = delta < 0
            ? Math.max(0, pos.row - 1)
            : Math.min(state.layout.length, pos.row + 1);
        placeSessionRow(name, insertAt);
        persistLayoutState();
        renderLayout();
        return;
    }
    // Hidden bucket: build the concrete ordering for the list this
    // session lives in, then swap it with its neighbour. The result
    // becomes the new user order.
    const liveNames = state.sessions.map(s => s.name);
    const bucket = state.hidden.has(name)
        ? liveNames.filter(n => state.hidden.has(n))
        : liveNames.filter(n => !state.hidden.has(n));
    const current = sortedSessionNames(bucket);
    const i = current.indexOf(name);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= current.length) return;
    [current[i], current[j]] = [current[j], current[i]];

    // Merge: both buckets are authoritative for their members; persist a
    // combined order so we don't drop ordering of the other bucket.
    const otherBucket = state.hidden.has(name)
        ? sortedSessionNames(liveNames.filter(n => !state.hidden.has(n)))
        : sortedSessionNames(liveNames.filter(n => state.hidden.has(n)));
    const newOrder = state.hidden.has(name)
        ? [...otherBucket, ...current]
        : [...current, ...otherBucket];
    state.order = newOrder;
    saveOrder(state.order);
    reappendInOrder();
}

function dropOnSession(targetName, draggedName, side = "top") {
    if (!draggedName || draggedName === targetName) return;
    if (side === "left" || side === "right") {
        putSessionBeside(targetName, draggedName, side);
        return;
    }
    if (side === "bottom") {
        placeSessionBelow(targetName, draggedName);
        return;
    }
    // "top" or any other value = insert above
    placeSessionAbove(targetName, draggedName);
}

function refreshHiddenChrome() {
    const wrap = document.getElementById("hidden-wrap");
    const count = document.getElementById("hidden-count");
    // Count only sessions that actually exist — stale entries in the set
    // (e.g., a killed session) shouldn't inflate the badge.
    const liveNames = new Set(state.sessions.map(s => s.name));
    let n = 0;
    for (const h of state.hidden) if (liveNames.has(h)) n += 1;
    count.textContent = String(n);
    wrap.hidden = n === 0;
    // Keep the Config > Pane Groups editor counts fresh too.
    if (typeof renderPaneGroupsEditor === "function") renderPaneGroupsEditor();
}

function toggleHidden(name) {
    if (state.hidden.has(name)) {
        state.hidden.delete(name);
    } else {
        state.hidden.add(name);
        // Hiding a pane also takes it out of any user-defined group so it's
        // only in one place at a time. Unhiding returns it to Visible, not
        // to its previous group (user can Move it back explicitly).
        if (state.groups.membership[name]) {
            delete state.groups.membership[name];
            saveGroups();
        }
        removeFromLayout(name);
    }
    saveHidden(state.hidden);
    persistLayoutState();
    const rec = state.nodes.get(name);
    if (rec) placePane(rec, name);
    refreshHiddenChrome();
    renderLayout();
}
