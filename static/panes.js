// panes.js — session pane construction, layout, drag/drop, modals, refresh
//
// Smaller features extracted to dedicated files under static/panes/:
//   idle-alerts.js   per-session idle alerts (config + firing)
//   hot-buttons.js   shared hot buttons + per-session hot loops
//   send-queue.js    send-bar single + repeat-with-cooldown queue
//   lifecycle.js     launch/stop ttyd, kill/new session, raw shells,
//                    iframe-fit helpers, restart dashboard

// Layout, ordering, drag-and-drop, hidden / pane-group bookkeeping
// moved to static/panes/layout.js. The functions remain accessible
// as top-level globals after lib/static.py concatenates the files.
//
// Removed from this file:
//   visibleSessionNames, hiddenSessionNames, sessionsInGroup
//   openMoveMenu, closeMoveMenu, _escCloseMoveMenu, moveSessionToGroup
//   flattenRows, normalizeLayoutRows, syncLayoutState, persistLayoutState
//   findLayoutPosition, removeFromLayout, placeSessionRow
//   putSessionBeside, placeSessionAbove, placeSessionBelow
//   _makeDropBar, renderLayout
//   sortedSessionNames, placePane, reappendInOrder
//   moveSession, dropOnSession, refreshHiddenChrome, toggleHidden

// (former layout block — see layout.js)


// idle alert editor + checkIdleAlerts + fireIdleAlert moved to
// static/panes/idle-alerts.js


// renderHotButtons / sendHotButton / toggleHotLoop / checkHotLoops /
// openHotButtons / closeHotButtons moved to static/panes/hot-buttons.js


// renderWorkflowEditor / openWorkflowEditor / closeWorkflowEditor /
// saveWorkflowEditor / clearWorkflowEditor / toggleWorkflowEnabled /
// loadWorkflowState and the split-picker quartet (openSplitPicker /
// closeSplitPicker / chooseSplitTarget / renderSplitPicker)
// moved to static/panes/modals.js
// hot-button modal handlers moved to static/panes/hot-buttons.js


// stopTtyd / killSession / stopRawShell / newSession / restartDashboard
// moved to static/panes/lifecycle.js


// Create a pane once per session and reuse it across refreshes, so active
// iframes aren't torn down and rebuilt every 5 s.
function createPane(s) {
    const id = cssId(s.name);
    const isRaw = s.kind === "raw";
    // Display label: raw shells get the friendly "shell · <uid>" prefix
    // (the underlying name keeps its ``raw-shell-`` prefix because that's
    // what every server-side pidfile / port-registry / stop call expects).
    const displayName = isRaw ? `shell · ${s.name}` : s.name;
    const sname = el("span", { class: "sname" }, displayName);
    const sbadges = el("span", { class: "sbadges" });
    const idle = el("span", { class: "dim" });
    const idleAlertBtn = el("button", {
        class: "btn blue summary-idle-alert",
        type: "button",
        onmousedown: (e) => {
            e.preventDefault();
            e.stopPropagation();
        },
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openIdleEditor(s.name);
        },
        title: "configure idle detection for this session",
    }, "Idle Alert");
    const idleIconBtn = el("button", {
        class: "wc-btn wc-idle-icon",
        type: "button",
        onmousedown: (e) => { e.preventDefault(); e.stopPropagation(); },
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); openIdleEditor(s.name); },
        title: "configure idle detection",
    });
    idleIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><ellipse cx="8" cy="8" rx="6.5" ry="4"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/></svg>';
    const idleWrap = el("span", { class: "summary-idle-wrap" }, idle, idleAlertBtn, idleIconBtn);
    const summaryTabLink = el("a", {
        class: "btn green summary-open",
        target: "_blank", rel: "noopener",
        title: "open ttyd in its own tab",
        onclick: stopSummaryToggle,
        href: "#",
        style: "display:none;text-decoration:none",
    }, "Open ↗");
    const logLink = el("a", {
        class: "btn summary-log",
        target: "_blank", rel: "noopener",
        title: "tmux scrollback for this session",
        onclick: stopSummaryToggle,
        href: `/api/session/log?session=${encodeURIComponent(s.name)}&html=1`,
        style: "text-decoration:none",
    }, "Log");
    const logIconBtn = el("a", {
        class: "wc-btn wc-log-icon",
        target: "_blank", rel: "noopener",
        title: "view tmux log (scrollback dump)",
        onclick: stopSummaryToggle,
        href: `/api/session/log?session=${encodeURIComponent(s.name)}&html=1`,
    });
    logIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><path d="M2 1h8l4 4v10H2V1zm8 0v4h4M4 8h8M4 11h6"/><path d="M2 1h8l4 4v10H2V1z" fill="none" stroke="currentColor" stroke-width="1.2"/><line x1="4" y1="8" x2="12" y2="8" stroke="currentColor" stroke-width="1"/><line x1="4" y1="10.5" x2="10" y2="10.5" stroke="currentColor" stroke-width="1"/><line x1="4" y1="6" x2="8" y2="6" stroke="currentColor" stroke-width="1"/></svg>';
    const scrollBtn = el("button", {
        class: "btn orange summary-scroll",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            enterCopyMode(s.name);
        },
        title: "enter tmux copy-mode so you can scroll back (equivalent to C-b [)",
    }, "Scroll");
    const scrollIconBtn = el("button", {
        class: "wc-btn wc-scroll-icon",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            enterCopyMode(s.name);
        },
        title: "enter tmux copy-mode (live scrollback — C-b [)",
    });
    scrollIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4l3-3 3 3"/><path d="M5 12l3 3 3-3"/><line x1="8" y1="1" x2="8" y2="15"/></svg>';
    const moveBtn = el("button", {
        class: "btn blue summary-move",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openMoveMenu(s.name, e.currentTarget);
        },
        title: "move this session to another pane group",
    }, "Move");
    const moveIconBtn = el("button", {
        class: "wc-btn wc-move-icon",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openMoveMenu(s.name, e.currentTarget);
        },
        title: "move this session to another pane group",
    });
    moveIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5.5 v7 a1 1 0 0 0 1 1 h11 a1 1 0 0 0 1 -1 v-6 a1 1 0 0 0 -1 -1 h-6 l-1.5 -1.5 h-3.5 a1 1 0 0 0 -1 1 z"/><path d="M7 9 h4 m0 0 l-1.5 -1.5 m1.5 1.5 l-1.5 1.5"/></svg>';
    const hideBtn = el("button", {
        class: "btn red summary-hide",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleHidden(s.name);
        },
        title: "move to the hidden list at the bottom of the page",
    }, "Hide");
    const hideIconBtn = el("button", {
        class: "wc-btn wc-hide-icon",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleHidden(s.name);
        },
        title: "hide this session",
    });
    hideIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><path d="M13 5c0-1-1.5-3-5-3S3 4 3 5c0 0-.5 0-1 .5S1.5 7 2 7h12c.5 0 .5-1 0-1.5S13 5 13 5zm-8.5 3a2.5 2.5 0 0 0-1.3 4.6c.3.2.7.4 1.3.4h7c.6 0 1-.2 1.3-.4A2.5 2.5 0 0 0 11.5 8h-7zM6 10.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm6 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/></svg>';
    const splitBtn = el("button", {
        class: "btn blue split-btn",
        type: "button",
        draggable: "true",
        onmousedown: (e) => {
            e.preventDefault();
            e.stopPropagation();
        },
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openSplitPicker(s.name);
        },
        ondragstart: (e) => {
            e.stopPropagation();
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/x-tmux-browse-split", s.name);
        },
        title: "click to place this session to the right of another; drag onto a session to snap left, right, or above",
    }, "▥");

    const upBtn = el("button", {
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); moveSession(s.name, -1); },
        title: "move up",
    }, "▲");
    const downBtn = el("button", {
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); moveSession(s.name, +1); },
        title: "move down",
    }, "▼");
    const reorderPad = el("span", {
        class: "reorder-pad",
        draggable: "true",
        title: "drag to reorder",
        ondragstart: (e) => {
            e.stopPropagation();
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/x-tmux-browse-session", s.name);
        },
        onclick: stopSummaryToggle,
    }, upBtn, downBtn);

    const msg = el("span", { id: "msg-" + id, class: "inline-msg dim" });

    const wcMinimize = el("button", {
        class: "wc-btn wc-minimize", type: "button",
        title: "minimize (furl pane)",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); if (details.open) details.open = false; },
    }, "\u2013");
    // Step buttons \u2014 adjust the iframe wrapper's pixel dimensions in
    // fixed increments, then run fit-to-iframe so tmux dimensions
    // catch up. Width is bounded to the parent layout row's width;
    // overshooting just clips. Height is unbounded.
    const mkStepBtn = (label, title, axis, delta) => {
        const btn = el("button", {
            class: "wc-btn wc-step", type: "button", title,
            onclick: (e) => {
                e.preventDefault(); e.stopPropagation();
                stepIframeSize(s.name, axis, delta);
            },
        }, label);
        return btn;
    };
    const wcMinusW = mkStepBtn("-w", "shrink iframe width by " + STEP_PX_W + "px", "w", -STEP_PX_W);
    const wcPlusW  = mkStepBtn("+w", "grow iframe width by "   + STEP_PX_W + "px", "w", +STEP_PX_W);
    const wcMinusH = mkStepBtn("-h", "shrink iframe height by " + STEP_PX_H + "px", "h", -STEP_PX_H);
    const wcPlusH  = mkStepBtn("+h", "grow iframe height by "   + STEP_PX_H + "px", "h", +STEP_PX_H);
    // Standalone tmux-resize button \u2014 fits the tmux window dimensions
    // to the iframe's actual pixel area (cols/rows derived from xterm
    // cell size). The previous ``resize-pane -Z`` toggle was a no-op
    // for the common single-pane window case, so this is the action
    // operators actually want here.
    const wcTmuxResize = el("button", {
        class: "wc-btn wc-tmux-resize", type: "button",
        title: "fit tmux window dimensions to the iframe area",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); fitTmuxToIframe(s.name); },
    });
    wcTmuxResize.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6V2h4"/><path d="M14 6V2h-4"/><path d="M2 10v4h4"/><path d="M14 10v4h-4"/></svg>';
    const wcMaximize = el("button", {
        class: "wc-btn wc-maximize", type: "button",
        title: "maximize: stretch iframe to 90vh and fit tmux to it",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            // Step 1: grow the iframe wrapper to (almost) the full
            // viewport. Step 2: wait one frame for the layout to
            // settle, then resize tmux to match the new iframe area.
            const rec = state.nodes.get(s.name);
            if (rec && rec.iframeWrap) {
                const cur = rec.iframeWrap.style.height;
                const maxH = "90vh";
                const defaultH = `${state.config.default_ttyd_height_vh || 70}vh`;
                rec.iframeWrap.style.height = cur === maxH ? defaultH : maxH;
            }
            requestAnimationFrame(() => fitTmuxToIframe(s.name));
        },
    }, "\u25a1");
    // Raw shells aren't tmux \u2014 closing them stops the ttyd directly
    // instead of running ``tmux kill-session`` (which would error).
    const closeAction = isRaw
        ? () => stopRawShell(s.name)
        : () => killSession(s.name);
    const wcClose = el("button", {
        class: "wc-btn wc-close", type: "button",
        title: isRaw ? "close (stop ttyd shell)" : "close (kill session)",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); closeAction(); },
    }, "\u00d7");
    const wcControls = el("span", { class: "wc-controls" },
        wcMinimize, wcMinusW, wcPlusW, wcMinusH, wcPlusH,
        wcTmuxResize, wcMaximize, wcClose);

    const summary = el("summary", { draggable: "true" },
        sname, msg, sbadges, idleWrap,
        el("span", { class: "summary-actions" },
            summaryTabLink, logLink, logIconBtn, scrollBtn, scrollIconBtn, splitBtn, moveBtn, moveIconBtn, hideBtn, hideIconBtn, reorderPad, wcControls),
    );
    const bodyKillBtn = el("button", {
        class: "btn red",
        onclick: closeAction,
    }, isRaw ? "Stop" : "Kill");
    const workflowBtn = el("button", {
        class: "btn blue", onclick: () => openWorkflowEditor(s.agent_name || ""),
        title: "edit scheduled prompts for this conversation-mode agent pane",
    }, "Workflows");
    const workflowToggleInput = el("input", {
        type: "checkbox",
        onchange: () => toggleWorkflowEnabled(s.agent_name || ""),
    });
    const workflowToggleText = el("span", { class: "workflow-switch-text" }, "Workflows");
    const workflowToggle = el("label", {
        class: "workflow-switch",
        title: "enable or disable scheduled workflow prompts for this agent conversation pane",
    }, workflowToggleInput, el("span", { class: "workflow-switch-track" }, el("span", { class: "workflow-switch-thumb" })), workflowToggleText);
    const hotManageBtn = el("button", {
        class: "btn blue", onclick: () => openHotButtons(s.name),
        title: "edit the shared hot buttons that appear in every session pane",
    }, "Hot Buttons");
    const hotPairs = Array.from({ length: 32 }, (_, idx) => {
        const cmdBtn = el("button", {
            class: "btn orange hot-chip",
            onclick: () => sendHotButton(s.name, idx),
            disabled: "disabled",
        });
        const loopBtn = el("button", {
            class: "btn orange hot-loop-btn",
            onclick: () => toggleHotLoop(s.name, idx),
            title: "start loop",
            type: "button",
        }, "⟳");
        const wrap = el("span", { class: "hot-pair", hidden: "hidden" }, cmdBtn, loopBtn);
        return { wrap, cmdBtn, loopBtn };
    });
    const launchBtn = el("button", { class: "btn green", onclick: () => launch(s.name) }, "Launch");
    const stopBtn = el("button", { class: "btn orange", onclick: () => stopTtyd(s.name) }, "Stop ttyd");
    const actions = el("div", { class: "pane-actions" },
        launchBtn, stopBtn, bodyKillBtn, workflowBtn, workflowToggle, msg, hotManageBtn, ...hotPairs.map((pair) => pair.wrap),
    );

    const iframe = el("iframe", {
        id: "iframe-" + id, class: "pane-iframe",
        allow: "clipboard-read; clipboard-write",
    });
    const dragShield = el("div", { class: "drag-shield" });
    const iframeWrap = el("div", { class: "ttyd-resize-wrap" }, iframe, dragShield);

    // Resize row together: when this pane's iframe wrapper is resized,
    // propagate the height to all sibling panes in the same layout row.
    let resizeSyncing = false;
    new ResizeObserver(() => {
        if (resizeSyncing || !state.config.resize_row_together) return;
        const pos = findLayoutPosition(s.name);
        if (!pos || !state.layout[pos.row] || state.layout[pos.row].length <= 1) return;
        const h = iframeWrap.style.height;
        if (!h) return;
        resizeSyncing = true;
        for (const peer of state.layout[pos.row]) {
            if (peer === s.name) continue;
            const peerRec = state.nodes.get(peer);
            if (peerRec && peerRec.iframeWrap) peerRec.iframeWrap.style.height = h;
        }
        resizeSyncing = false;
    }).observe(iframeWrap);

    const sendInput = el("input", {
        type: "text", class: "send-bar-input",
        placeholder: `Send to ${s.name}...`,
    });
    const sendCount = el("input", {
        type: "number", class: "send-bar-count",
        min: "1", max: "99", step: "1", value: "1",
        title: ("send N times — repeats wait for the pane to go idle "
            + "plus a 60s cooldown, with a re-check before each send"),
    });
    const sendBtn = el("button",
        { class: "btn green", onclick: () => sendToPane(s.name, sendInput, sendCount) },
        "Send");
    sendInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendToPane(s.name, sendInput, sendCount);
    });
    const sendStatus = el("span", { class: "send-bar-status dim" });
    const sendBar = el("div", { class: "send-bar" },
        sendInput, sendCount, sendBtn, sendStatus);

    const phoneKeys = el("div", { class: "phone-keys" },
        ...loadPhoneKeys().map((def) =>
            el("button", {
                class: "phone-key", type: "button",
                onclick: () => { if (def.keys && def.keys.length) sendKeysToPane(s.name, def.keys); },
            }, def.label),
        ),
    );

    const fPort = el("span"), fPid = el("span"), fCreated = el("span");
    const footer = el("div", { class: "pane-footer" }, fPort, fPid, fCreated);

    const dropOverlay = el("div", { class: "drop-overlay" });
    const details = el("details", {
        class: isRaw ? "session session-raw" : "session",
        "data-session": s.name,
    },
        summary, el("div", { class: "pane-body" }, actions, iframeWrap, sendBar, phoneKeys, footer),
        dropOverlay,
    );

    details.addEventListener("toggle", () => {
        if (details.open && state.config.launch_on_expand && !state.openPanes.has(s.name)) {
            launch(s.name);
        }
        // Furl side-by-side: when one pane in a row closes, close all in the row
        if (!details.open && state.config.furl_side_by_side) {
            const pos = findLayoutPosition(s.name);
            if (pos && state.layout[pos.row] && state.layout[pos.row].length > 1) {
                for (const peer of state.layout[pos.row]) {
                    if (peer === s.name) continue;
                    const peerRec = state.nodes.get(peer);
                    if (peerRec && peerRec.details.open) peerRec.details.open = false;
                }
            }
        }
        if (details.open && state.config.furl_side_by_side) {
            const pos = findLayoutPosition(s.name);
            if (pos && state.layout[pos.row] && state.layout[pos.row].length > 1) {
                for (const peer of state.layout[pos.row]) {
                    if (peer === s.name) continue;
                    const peerRec = state.nodes.get(peer);
                    if (peerRec && !peerRec.details.open) peerRec.details.open = true;
                }
            }
        }
    });

    // Summary bar drag: dropping on left/right half of another session
    // snaps side-by-side; dropping above (center) reorders.
    summary.addEventListener("dragstart", (e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/x-tmux-browse-split", s.name);
        e.dataTransfer.setData("text/x-tmux-browse-session", s.name);
    });

    // Drag-and-drop with tilix-style 4-zone triangle detection.
    // The pane is divided into 4 triangles meeting at the center point:
    //   LEFT:   (0,0) → (0,H) → (W/2,H/2)
    //   RIGHT:  (W,0) → (W,H) → (W/2,H/2)
    //   TOP:    (0,0) → (W,0) → (W/2,H/2)
    //   BOTTOM: (0,H) → (W,H) → (W/2,H/2)
    const DROP_ZONES = ["drop-left", "drop-right", "drop-top", "drop-bottom"];
    const clearDropClasses = () => details.classList.remove(...DROP_ZONES);

    function getDropZone(e) {
        const rect = details.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const w = rect.width;
        const h = rect.height;
        if (w < 1 || h < 1) return null;
        // Normalize to 0..1
        const nx = x / w;
        const ny = y / h;
        // The two diagonals divide the rectangle into 4 triangles:
        // diagonal 1: top-left to bottom-right (ny = nx)
        // diagonal 2: top-right to bottom-left (ny = 1 - nx)
        const aboveDiag1 = ny < nx;
        const aboveDiag2 = ny < (1 - nx);
        if (aboveDiag2 && !aboveDiag1) return "left";
        if (aboveDiag1 && aboveDiag2) return "top";
        if (aboveDiag1 && !aboveDiag2) return "right";
        return "bottom";
    }

    details.addEventListener("dragover", (e) => {
        const hasDrag = e.dataTransfer.types.includes("text/x-tmux-browse-split") ||
                        e.dataTransfer.types.includes("text/x-tmux-browse-session");
        if (!hasDrag) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        clearDropClasses();
        const zone = getDropZone(e);
        if (zone) details.classList.add("drop-" + zone);
    });
    details.addEventListener("dragleave", (e) => {
        // Only clear if actually leaving the details element, not moving between children
        if (!details.contains(e.relatedTarget)) clearDropClasses();
    });
    details.addEventListener("drop", (e) => {
        const draggedSplit = e.dataTransfer.getData("text/x-tmux-browse-split");
        const draggedReorder = e.dataTransfer.getData("text/x-tmux-browse-session");
        clearDropClasses();
        if (!draggedSplit && !draggedReorder) return;
        e.preventDefault();
        const zone = getDropZone(e);
        const name = draggedSplit || draggedReorder;
        dropOnSession(s.name, name, zone || "top");
    });

    return {
        details, sbadges, idle, idleWrap, idleAlertBtn, idleIconBtn,
        summaryTabLink, logLink, logIconBtn, scrollBtn, scrollIconBtn, splitBtn, moveBtn, moveIconBtn, hideBtn, hideIconBtn, reorderPad,
        launchBtn, stopBtn, killBtn: bodyKillBtn, hotManageBtn, msg,
        wcClose, wcMaximize, wcMinimize, wcTmuxResize,
        wcPlusW, wcMinusW, wcPlusH, wcMinusH,
        workflowBtn, workflowToggle, workflowToggleInput, workflowToggleText,
        iframe, iframeWrap, sendBar, sendStatus, phoneKeys, fPort, fPid, fCreated, footer,
        hotPairs,
    };
}


function updatePane(rec, s) {
    const cfg = state.config;
    // Badges
    rec.sbadges.textContent = "";
    if (cfg.show_attached_badge && s.attached > 0) {
        rec.sbadges.append(el("span", { class: "badge attached" }, `${s.attached} clients`));
    }
    if (cfg.show_window_badge) {
        rec.sbadges.append(el("span", { class: "badge" }, `${s.windows}w`));
    }
    if (cfg.show_port_badge && s.ttyd_running) {
        rec.sbadges.append(el("span", { class: "badge running" }, `:${s.port}`));
    }
    // Prefer the server-computed ages to avoid clock-skew surprises.
    rec.idle.textContent = `idle ${s.idle_seconds !== undefined
        ? fmtAgeSeconds(s.idle_seconds)
        : fmtAge(s.activity)}`;
    const idleCfg = idleAlertFor(s.name);
    rec.idleAlertBtn.textContent = idleCfg.enabled
        ? `Idle Alert ${fmtAgeSeconds(idleCfg.thresholdSec)}`
        : "Idle Alert";
    rec.idleAlertBtn.className = idleCfg.enabled
        ? "btn green summary-idle-alert"
        : "btn blue summary-idle-alert";
    rec.idleAlertBtn.title = idleCfg.enabled
        ? `enabled: ${idleCfg.sound ? "sound" : ""}${idleCfg.sound && idleCfg.prompt ? " + " : ""}${idleCfg.prompt ? "prompt" : ""}`
        : "configure idle detection for this session";
    rec.idleIconBtn.style.color = idleCfg.enabled ? "var(--green)" : "";

    // Summary "Open" button: hidden entirely until ttyd is running.
    const url = s.ttyd_running ? ttydUrl(s.port) : "#";
    rec.summaryTabLink.href = url;
    rec.summaryTabLink.dataset.available = s.ttyd_running ? "1" : "0";

    // Footer — make the "port N" tag a link that opens the ttyd in a new tab.
    rec.fPort.textContent = "";
    if (s.ttyd_running && s.port) {
        const a = el("a", {
            class: "summary-link",
            target: "_blank", rel: "noopener",
            href: url,
            title: "open ttyd in a new tab",
        }, `ttyd on port ${s.port} ↗`);
        rec.fPort.append(a);
    } else {
        rec.fPort.textContent = `port ${s.port || "—"}`;
    }
    rec.fPid.textContent = `pid ${s.pid || "—"}`;
    rec.fCreated.textContent = `created ${s.created_seconds_ago !== undefined
        ? fmtAgeSeconds(s.created_seconds_ago)
        : fmtAge(s.created)} ago`;
    const workflow = s.agent_name ? workflowEntry(s.agent_name) : { enabled: false };
    rec.workflowToggleInput.checked = !!workflow.enabled;
    rec.workflowToggle.classList.toggle("is-on", !!workflow.enabled);
    rec.workflowToggleText.textContent = workflow.enabled ? "Workflows On" : "Workflows Off";
    setVisible(rec.workflowBtn, !!s.conversation_mode, "");
    setVisible(rec.workflowToggle, !!s.conversation_mode, "inline-flex");

    // Iframe src: set it once when ttyd comes up AND pane is open;
    // never blow it away on refresh unless ttyd went down.
    const iframeUrl = s.ttyd_running ? ttydUrl(s.port) : null;
    const cur = rec.iframe.getAttribute("src") || "";
    if (iframeUrl && state.openPanes.has(s.name) && cur !== iframeUrl) {
        rec.iframe.setAttribute("src", iframeUrl);
    }
    if (!iframeUrl && cur) {
        rec.iframe.removeAttribute("src");
    }
    renderHotButtons(s.name);
    applyDashboardConfigToPane(rec);
}

// sortedSessionNames / placePane / reappendInOrder / moveSession /
// dropOnSession / refreshHiddenChrome / toggleHidden moved to
// static/panes/layout.js

async function refresh() {
    const r = await api("GET", "/api/sessions");
    const sessions = (r && r.sessions) || [];
    state.sessions = sessions;
    showTmuxUnreachableBanner(!!(r && r.tmux_unreachable));
    checkIdleAlerts(sessions);
    await checkHotLoops(sessions);
    await checkSendQueue(sessions);
    const root = document.getElementById("sessions");
    const seen = new Set();

    // Index the raw session list by name so we can walk it in user order.
    const byName = new Map(sessions.map(s => [s.name, s]));
    for (const name of sortedSessionNames(sessions.map(s => s.name))) {
        const s = byName.get(name);
        seen.add(name);
        let rec = state.nodes.get(name);
        if (!rec) {
            rec = createPane(s);
            state.nodes.set(name, rec);
        }
        placePane(rec, name);
        updatePane(rec, s);
    }
    // Remove panes for sessions that no longer exist
    for (const [name, rec] of state.nodes) {
        if (!seen.has(name)) {
            rec.details.remove();
            state.nodes.delete(name);
            state.openPanes.delete(name);
        }
    }

    // Prune hidden-set entries for sessions that no longer exist so the list
    // doesn't grow forever as sessions come and go.
    let changed = false;
    for (const h of [...state.hidden]) {
        if (!seen.has(h)) { state.hidden.delete(h); changed = true; }
    }
    if (changed) saveHidden(state.hidden);

    // Same treatment for state.order — otherwise it grows monotonically
    // as sessions come and go over a long-lived page session.
    const prevOrderLen = state.order.length;
    state.order = state.order.filter(n => seen.has(n));
    if (state.order.length !== prevOrderLen) saveOrder(state.order);

    document.getElementById("count").textContent =
        `${sessions.length} session${sessions.length === 1 ? "" : "s"}`;
    callExt("renderAgentsPane");
    callExt("renderPaneAdmin");
    renderLayout();
    if (state.splitPicker.open) renderSplitPicker();
}

// Surface "tmux server is unreachable" prominently — without this the
// dashboard silently shows "0 sessions" when tmux is hung (memory
// pressure, stuck client) and operators chase ghosts in the dashboard
// code. The banner is purely informational; raw-shell rows still render
// normally underneath.
function showTmuxUnreachableBanner(show) {
    let banner = document.getElementById("tmux-unreachable-banner");
    if (!show) {
        if (banner) banner.hidden = true;
        return;
    }
    if (!banner) {
        banner = document.createElement("div");
        banner.id = "tmux-unreachable-banner";
        banner.className = "ext-restart-banner";
        banner.style.background = "#3b1117";
        banner.style.borderColor = "#8b1e2d";
        banner.textContent = "tmux server is not responding — session list is unavailable. " +
            "Check `tmux ls` from a shell; the server may be wedged (memory pressure, stuck client).";
        const sessionsEl = document.getElementById("sessions");
        sessionsEl.parentNode.insertBefore(banner, sessionsEl);
    }
    banner.hidden = false;
}

// Null-safe wiring helper. Many of the bindings below target DOM IDs
// or handler functions that only exist when an extension is loaded
// (the agent extension contributes the workflow / step-viewer / agent
// editor markup and code; without it those getElementById calls return
// null and the surrounding init would crash, taking the whole
// dashboard with it). ``bind`` skips silently when either side is
// missing so a no-extensions install still boots.
function bind(id, event, handler) {
    const el = document.getElementById(id);
    if (!el || typeof handler !== "function") return;
    el.addEventListener(event, handler);
}

// Extension-call shims. The agent extension exposes its handlers as
// loose globals (window.loadAgents, window.renderAgentsPane, …);
// without it the names are undefined and a direct call throws
// ReferenceError, taking down whichever init/refresh path made the
// call. These helpers funnel every "is the extension here?" check
// through one place — adding a new extension call is just
// ``callExt("foo")`` instead of remembering to write a typeof guard
// at every site.
function callExt(name, ...args) {
    const fn = (typeof window !== "undefined") ? window[name] : undefined;
    return (typeof fn === "function") ? fn(...args) : undefined;
}
async function awaitExt(name, ...args) {
    const fn = (typeof window !== "undefined") ? window[name] : undefined;
    return (typeof fn === "function") ? await fn(...args) : undefined;
}
// Variant of ``bind`` that resolves the handler by name — used when the
// handler itself lives in an extension. Skips silently if either the
// element or the named global is missing.
function bindExt(id, event, handlerName) {
    const fn = (typeof window !== "undefined") ? window[handlerName] : undefined;
    bind(id, event, typeof fn === "function" ? fn : null);
}

document.addEventListener("DOMContentLoaded", async () => {
    // Shield iframes during any drag so drag events reach parent panes
    document.addEventListener("dragstart", () => document.body.classList.add("dragging"));
    document.addEventListener("dragend", () => document.body.classList.remove("dragging"));

    document.getElementById("refresh-btn").addEventListener("click", refresh);
    document.getElementById("new-btn").addEventListener("click", newSession);
    document.getElementById("raw-btn").addEventListener("click", openRawTtyd);
    document.getElementById("restart-btn").addEventListener("click", restartDashboard);
    document.getElementById("os-restart-btn").addEventListener("click", restartDashboard);
    document.getElementById("tmux-help-btn").addEventListener("click", () => {
        document.getElementById("tmux-help-modal").hidden = false;
        syncModalChrome();
    });
    document.getElementById("tmux-help-close-btn").addEventListener("click", () => {
        document.getElementById("tmux-help-modal").hidden = true;
        syncModalChrome();
    });
    document.getElementById("tmux-help-modal").addEventListener("click", (e) => {
        if (e.target.id === "tmux-help-modal") {
            document.getElementById("tmux-help-modal").hidden = true;
            syncModalChrome();
        }
    });
    document.getElementById("launch-claude-btn").addEventListener("click", () => launchCodingSession("claude", "claude"));
    document.getElementById("launch-claude-yolo-btn").addEventListener("click", () => launchCodingSession("claude-yolo", "claude --dangerously-skip-permissions"));
    document.getElementById("launch-codex-btn").addEventListener("click", () => launchCodingSession("codex", "codex"));
    document.getElementById("launch-codex-yolo-btn").addEventListener("click", () => launchCodingSession("codex-yolo", "codex --full-auto"));
    document.getElementById("launch-kimi-btn").addEventListener("click", () => launchCodingSession("kimi", "kimi-code"));
    document.getElementById("launch-kimi-yolo-btn").addEventListener("click", () => launchCodingSession("kimi-yolo", "kimi-code --yolo"));
    document.getElementById("launch-monitor-btn").addEventListener("click", () => launchCodingSession("sysmon", "sysmon"));
    document.getElementById("launch-top-btn").addEventListener("click", () => launchCodingSession("top", "systop"));
    document.getElementById("cfg-save-btn").addEventListener("click", saveDashboardConfig);
    document.getElementById("cfg-load-btn").addEventListener("click", reloadDashboardConfig);
    document.getElementById("cfg-reset-btn").addEventListener("click", resetDashboardConfig);
    document.getElementById("client-nick-btn").addEventListener("click", setClientNickname);
    document.getElementById("config-wrap").addEventListener("click", guardConfigOpen);
    document.getElementById("cfg-clear-cache-btn").addEventListener("click", clearLocalCache);
    document.getElementById("pane-group-add-btn").addEventListener("click", addPaneGroup);
    document.getElementById("pane-group-new-name").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); addPaneGroup(); }
    });
    document.getElementById("phone-key-add-btn").addEventListener("click", addPhoneKey);
    document.getElementById("phone-key-reset-btn").addEventListener("click", resetPhoneKeys);
    document.getElementById("cfg-lock-set-btn").addEventListener("click", setConfigLock);
    document.getElementById("cfg-lock-clear-btn").addEventListener("click", clearConfigLock);
    bindExt("hooks-save-btn", "click", "saveHooks");
    bindExt("hooks-reset-btn", "click", "resetHooks");
    bindExt("conductor-save-btn", "click", "saveConductor");
    bindExt("conductor-reload-btn", "click", "loadConductor");
    document.getElementById("cfg-toggle-all-topbar").addEventListener("click", (e) => toggleAllSection(TOPBAR_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-toggle-all-summary").addEventListener("click", (e) => toggleAllSection(SUMMARY_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-toggle-all-body").addEventListener("click", (e) => toggleAllSection(BODY_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-sound-test").addEventListener("click", () => {
        primeAudio();
        playIdleTone(document.getElementById("cfg-idle-sound").value);
    });
    // Agent-extension-only bindings — bindExt skips silently when the
    // extension isn't installed, so a no-extensions install still
    // finishes init.
    bindExt("cfg-agent-save-btn", "click", "saveAgentConfig");
    bind("cfg-agent-reload-btn", "click", async () => {
        const ok = await awaitExt("loadAgents");
        if (ok) callExt("setAgentStatus", "reloaded agent list", "ok");
    });
    bindExt("cfg-agent-remove-btn", "click", "removeAgentConfig");
    bindExt("agent-steps-close-btn", "click", "closeAgentSteps");
    bindExt("runs-search-btn", "click", "searchRuns");
    bind("runs-search-q", "keydown", (e) => {
        if (e.key === "Enter") callExt("searchRuns");
    });
    bindExt("task-create-btn", "click", "createTask");
    const fm = callExt("agentFieldMap");
    if (fm) {
        if (fm.existing) fm.existing.addEventListener("change", loadExistingAgentIntoForm);
        if (fm.preset) fm.preset.addEventListener("change", applyAgentPreset);
        if (fm.name) fm.name.addEventListener("input", () => {
            const fields = callExt("agentFieldMap");
            if (!fields) return;
            if (fields.existing.value && fields.name.value.trim() !== fields.existing.value) fields.existing.value = "";
            const constraint = callExt("enforceAgentConstraint");
            if (constraint) callExt("setAgentStatus", constraint.message, "dim");
        });
    }
    for (const input of Object.values(configFieldMap())) {
        if (!input) continue;
        input.addEventListener("input", previewDashboardConfig);
        input.addEventListener("change", previewDashboardConfig);
    }
    document.getElementById("hot-close-btn").addEventListener("click", closeHotButtons);
    document.getElementById("hot-save-btn").addEventListener("click", saveHotButton);
    document.getElementById("hot-clear-btn").addEventListener("click", clearHotButton);
    bind("workflow-close-btn", "click", closeWorkflowEditor);
    bindExt("workflow-save-btn", "click", "saveWorkflowEditor");
    bindExt("workflow-clear-btn", "click", "clearWorkflowEditor");
    document.getElementById("idle-close-btn").addEventListener("click", closeIdleEditor);
    document.getElementById("idle-save-btn").addEventListener("click", saveIdleEditor);
    document.getElementById("idle-clear-btn").addEventListener("click", clearIdleEditor);
    document.getElementById("split-close-btn").addEventListener("click", closeSplitPicker);
    document.getElementById("split-search").addEventListener("input", (e) => {
        state.splitPicker.filter = e.target.value || "";
        renderSplitPicker();
    });
    bind("agent-steps-modal", "click", (e) => {
        if (e.target.id === "agent-steps-modal") callExt("closeAgentSteps");
    });
    bind("workflow-modal", "click", (e) => {
        if (e.target.id === "workflow-modal") closeWorkflowEditor();
    });
    document.getElementById("hot-modal").addEventListener("click", (e) => {
        if (e.target.id === "hot-modal") closeHotButtons();
    });
    document.getElementById("idle-modal").addEventListener("click", (e) => {
        if (e.target.id === "idle-modal") closeIdleEditor();
    });
    document.getElementById("split-modal").addEventListener("click", (e) => {
        if (e.target.id === "split-modal") closeSplitPicker();
    });
    document.getElementById("new-name").addEventListener("keydown", (e) => {
        if (e.key === "Enter") newSession();
    });
    document.addEventListener("pointerdown", primeAudio, { passive: true });
    document.addEventListener("keydown", primeAudio);
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (state.stepViewer && state.stepViewer.open) callExt("closeAgentSteps");
        if (state.hotEditor.open) closeHotButtons();
        if (state.workflowEditor && state.workflowEditor.open) closeWorkflowEditor();
        if (state.idleEditor.open) closeIdleEditor();
        if (state.splitPicker.open) closeSplitPicker();
    });
    renderConfigForm();
    checkImportCfgParam();
    applyTopbarConfig();
    callExt("renderAgentSelectors");
    renderPhoneKeysPreview();
    await checkConfigLock();
    await loadDashboardConfig();
    await awaitExt("loadAgents");
    callExt("populateRunAgentFilter");
    callExt("populateTaskAgentSelect");
    await awaitExt("loadAgentWorkflows");
    await refresh();
    await awaitExt("searchRuns");
    await awaitExt("loadTasks");
    await awaitExt("loadCostSummary");
    await awaitExt("loadHooks");
    await awaitExt("loadConductor");
    await awaitExt("loadNotifications");
    await loadClients();
    scheduleRefreshLoop();
    setInterval(pollIdleOnly, 60000);
    setInterval(loadClients, 15000);
    setInterval(checkClientInbox, 10000);
});
