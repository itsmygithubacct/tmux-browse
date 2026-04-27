// Modal dialogs that aren't tied to a single feature elsewhere:
//
// - Workflow editor (per-agent scheduled prompts). The HTML lives in
//   the agent extension's ui_blocks.html, so every entry point bails
//   out cleanly when the modal element isn't in the DOM. The internal
//   calls to workflowEntry / saveAgentWorkflows are guarded
//   structurally — those globals only exist when the agent extension
//   is loaded, which is the same condition that puts the workflow
//   buttons on the page in the first place.
//
// - Split picker (place-this-pane-beside-that one). This is core
//   functionality that uses the shared layout helpers in panes.js.

function renderWorkflowEditor() {
    const title = document.getElementById("workflow-modal-title");
    const list = document.getElementById("workflow-slot-list");
    const nameInp = document.getElementById("workflow-name");
    const promptInp = document.getElementById("workflow-prompt");
    const intervalInp = document.getElementById("workflow-interval");
    if (!title || !list || !nameInp || !promptInp || !intervalInp) return;
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    const slots = entry.workflows;
    const row = slots[slot] || { name: "", prompt: "", interval_seconds: 300 };
    title.textContent = `Agent Workflows · ${agent}`;
    nameInp.value = row.name;
    promptInp.value = row.prompt;
    intervalInp.value = row.interval_seconds;
    list.textContent = "";
    slots.forEach((workflow, idx) => {
        const present = !!workflow.prompt.trim();
        list.append(el("button", {
            class: idx === slot ? "hot-slot-item active" : "hot-slot-item",
            type: "button",
            onclick: () => {
                state.workflowEditor.slot = idx;
                renderWorkflowEditor();
            },
        },
        el("span", { class: "hot-slot-kicker" }, `Workflow ${idx + 1}`),
        el("span", { class: "hot-slot-name" }, workflow.name || (present ? `Every ${workflow.interval_seconds}s` : "Empty slot")),
        el("span", { class: "hot-slot-command" }, present ? workflow.prompt : "Create scheduled workflow"),
        ));
    });
}

function openWorkflowEditor(agentName, slot = 0) {
    const modal = document.getElementById("workflow-modal");
    if (!modal) return;
    state.workflowEditor.open = true;
    state.workflowEditor.agent = (agentName || "").trim().toLowerCase();
    state.workflowEditor.slot = slot;
    workflowEntry(state.workflowEditor.agent);
    renderWorkflowEditor();
    modal.hidden = false;
    syncModalChrome();
}

function closeWorkflowEditor() {
    const modal = document.getElementById("workflow-modal");
    state.workflowEditor.open = false;
    if (modal) modal.hidden = true;
    syncModalChrome();
}

async function saveWorkflowEditor() {
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    entry.workflows[slot] = normalizeWorkflowSlot({
        name: document.getElementById("workflow-name").value,
        prompt: document.getElementById("workflow-prompt").value,
        interval_seconds: document.getElementById("workflow-interval").value,
    });
    await saveAgentWorkflows(true);
    renderWorkflowEditor();
    refresh();
}

async function clearWorkflowEditor() {
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    entry.workflows[slot] = { name: "", prompt: "", interval_seconds: 300 };
    await saveAgentWorkflows(true);
    renderWorkflowEditor();
    refresh();
}

async function toggleWorkflowEnabled(agentName) {
    const entry = workflowEntry(agentName);
    entry.enabled = !entry.enabled;
    // Workflow execution is server-side; toggling just saves config.
    await saveAgentWorkflows(true);
    refresh();
}

async function loadWorkflowState() {
    const r = await api("GET", "/api/agent-workflow-state");
    if (r.ok) {
        state.workflowServerState = r.state || {};
        state.schedulerRunning = !!r.scheduler_running;
    }
}

function openSplitPicker(session) {
    state.splitPicker.open = true;
    state.splitPicker.session = session;
    state.splitPicker.filter = "";
    renderSplitPicker();
    document.getElementById("split-modal").hidden = false;
    syncModalChrome();
    const search = document.getElementById("split-search");
    if (search) search.focus();
}

function closeSplitPicker() {
    state.splitPicker.open = false;
    document.getElementById("split-modal").hidden = true;
    syncModalChrome();
}

function chooseSplitTarget(targetName) {
    putSessionBeside(targetName, state.splitPicker.session, "right");
    closeSplitPicker();
}

function renderSplitPicker() {
    const source = state.splitPicker.session;
    const list = document.getElementById("split-target-list");
    const title = document.getElementById("split-modal-title");
    const filter = state.splitPicker.filter.trim().toLowerCase();
    title.textContent = `Split Right · ${source}`;
    list.textContent = "";
    const candidates = state.sessions
        .filter((s) => s.name !== source && !state.hidden.has(s.name))
        .filter((s) => !filter || s.name.toLowerCase().includes(filter));
    if (!candidates.length) {
        list.append(el("div", { class: "dim split-empty" },
            filter
                ? "No visible sessions match that filter."
                : "No other visible sessions are available."));
        return;
    }
    for (const s of candidates) {
        list.append(el("button", {
            class: "split-target-item",
            type: "button",
            onclick: () => chooseSplitTarget(s.name),
            title: `place ${source} to the right of ${s.name}`,
        },
            el("div", { class: "split-target-title" },
                s.name,
                el("span", { class: "badge" }, `${s.windows}w`),
                s.attached > 0 ? el("span", { class: "badge attached" }, `${s.attached} clients`) : null,
            ),
            el("div", { class: "split-target-meta" },
                `idle ${s.idle_seconds !== undefined ? fmtAgeSeconds(s.idle_seconds) : fmtAge(s.activity)}`),
        ));
    }
}
