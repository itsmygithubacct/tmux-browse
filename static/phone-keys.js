// phone-keys.js — mobile key customization

// --- Phone keys config ---

const DEFAULT_PHONE_KEYS = [
    { label: "\u2191", keys: ["Up"] },
    { label: "\u2193", keys: ["Down"] },
    { label: "\u2190", keys: ["Left"] },
    { label: "\u2192", keys: ["Right"] },
    { label: "Esc", keys: ["Escape"] },
    { label: "C-c", keys: ["C-c"] },
    { label: "C-b", keys: ["C-b"] },
    { label: "Shift", keys: [] },
    { label: "PgUp", keys: ["PageUp"] },
    { label: "PgDn", keys: ["PageDown"] },
    { label: "\u23CE", keys: ["Enter"] },
];

function loadPhoneKeys() {
    return loadJSON(PHONE_KEYS_KEY, null) || [...DEFAULT_PHONE_KEYS];
}

function savePhoneKeys(keys) {
    saveJSON(PHONE_KEYS_KEY, keys);
}

function renderPhoneKeysPreview() {
    const root = document.getElementById("phone-keys-preview");
    if (!root) return;
    root.innerHTML = "";
    const keys = loadPhoneKeys();
    keys.forEach((def, idx) => {
        const btn = el("button", {
            class: "phone-key", type: "button", draggable: "true",
            title: `tmux: ${(def.keys || []).join(" ") || "(none)"} — click to remove`,
            onclick: () => {
                keys.splice(idx, 1);
                savePhoneKeys(keys);
                renderPhoneKeysPreview();
            },
        }, def.label);
        btn.addEventListener("dragstart", (e) => {
            e.dataTransfer.setData("text/x-phone-key-idx", String(idx));
            e.dataTransfer.effectAllowed = "move";
        });
        btn.addEventListener("dragover", (e) => {
            if (e.dataTransfer.types.includes("text/x-phone-key-idx")) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
            }
        });
        btn.addEventListener("drop", (e) => {
            const fromIdx = parseInt(e.dataTransfer.getData("text/x-phone-key-idx"), 10);
            if (isNaN(fromIdx) || fromIdx === idx) return;
            e.preventDefault();
            const [moved] = keys.splice(fromIdx, 1);
            keys.splice(idx, 0, moved);
            savePhoneKeys(keys);
            renderPhoneKeysPreview();
        });
        root.append(btn);
    });
}

function addPhoneKey() {
    const labelInput = document.getElementById("phone-key-label");
    const tmuxInput = document.getElementById("phone-key-tmux");
    const label = (labelInput.value || "").trim();
    const tmux = (tmuxInput.value || "").trim();
    if (!label || !tmux) return;
    const keys = loadPhoneKeys();
    keys.push({ label, keys: [tmux] });
    savePhoneKeys(keys);
    labelInput.value = "";
    tmuxInput.value = "";
    renderPhoneKeysPreview();
}

function resetPhoneKeys() {
    savePhoneKeys([...DEFAULT_PHONE_KEYS]);
    renderPhoneKeysPreview();
}

