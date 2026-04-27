// SGR (ANSI color/style) -> HTML conversion for the per-session
// preview tiles. Adapted from muxplex's ansiToHtml (MIT-licensed).
// Covers the 16-color palette + 256-color foreground/background;
// truecolor (38;2;r;g;b) is rare in scrollback and not handled.
//
// Output is a string of <span style="..."> wrappers around the
// raw text; HTML special characters are escaped. Caller drops the
// result into a <pre> with monospace styling.

const ANSI_PALETTE = [
    "#2e3436", "#cc0000", "#4e9a06", "#c4a000",
    "#3465a4", "#75507b", "#06989a", "#d3d7cf",
    "#555753", "#ef2929", "#8ae234", "#fce94f",
    "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
];

function _ansi256(c) {
    // Standard 16
    if (c < 16) return ANSI_PALETTE[c];
    // 6×6×6 cube
    if (c < 232) {
        const n = c - 16;
        const r = Math.floor(n / 36);
        const g = Math.floor((n % 36) / 6);
        const b = n % 6;
        const conv = (v) => v === 0 ? 0 : 55 + v * 40;
        return `rgb(${conv(r)},${conv(g)},${conv(b)})`;
    }
    // Greyscale ramp
    const v = 8 + (c - 232) * 10;
    return `rgb(${v},${v},${v})`;
}

function _ansiParamsToStyle(params) {
    const styles = [];
    let k = 0;
    while (k < params.length) {
        const p = parseInt(params[k], 10) || 0;
        if (p === 0) return "reset";
        else if (p === 1) styles.push("font-weight:bold");
        else if (p === 2) styles.push("opacity:0.7");
        else if (p === 3) styles.push("font-style:italic");
        else if (p === 4) styles.push("text-decoration:underline");
        else if (p === 7) styles.push("filter:invert(1)");
        else if (p === 9) styles.push("text-decoration:line-through");
        else if (p >= 30 && p <= 37) styles.push("color:" + ANSI_PALETTE[p - 30]);
        else if (p === 38 && params[k + 1] === "5") {
            const c = parseInt(params[k + 2], 10) || 0;
            styles.push("color:" + _ansi256(c));
            k += 2;
        }
        else if (p === 39) styles.push("color:inherit");
        else if (p >= 40 && p <= 47) styles.push("background:" + ANSI_PALETTE[p - 40]);
        else if (p === 48 && params[k + 1] === "5") {
            const c = parseInt(params[k + 2], 10) || 0;
            styles.push("background:" + _ansi256(c));
            k += 2;
        }
        else if (p === 49) styles.push("background:inherit");
        else if (p >= 90 && p <= 97) styles.push("color:" + ANSI_PALETTE[p - 90 + 8]);
        else if (p >= 100 && p <= 107) styles.push("background:" + ANSI_PALETTE[p - 100 + 8]);
        k++;
    }
    return styles.join(";");
}

function ansiToHtml(raw) {
    if (!raw) return "";
    let out = "";
    let spans = 0;
    let i = 0;
    const len = raw.length;
    while (i < len) {
        // SGR sequence: ESC [ ... m
        if (raw[i] === "\x1b" && raw[i + 1] === "[") {
            let j = i + 2;
            while (j < len && raw[j] !== "m" && j - i < 20) j++;
            if (j < len && raw[j] === "m") {
                const params = raw.substring(i + 2, j).split(";");
                const style = _ansiParamsToStyle(params);
                if (style === "reset") {
                    while (spans > 0) { out += "</span>"; spans--; }
                } else if (style) {
                    out += `<span style="${style}">`;
                    spans++;
                }
                i = j + 1;
                continue;
            }
        }
        const ch = raw[i];
        if (ch === "<") out += "&lt;";
        else if (ch === ">") out += "&gt;";
        else if (ch === "&") out += "&amp;";
        else if (ch === '"') out += "&quot;";
        else out += ch;
        i++;
    }
    while (spans > 0) { out += "</span>"; spans--; }
    return out;
}

// Trim trailing blank lines from the snapshot before slicing the
// "last N rows" — sessions with the cursor near the top (e.g. fresh
// shell) have content at rows 1-2 and rows 3-N blank; slicing first
// would grab N blank rows. (Lesson from muxplex's implementation.)
function trimTrailingBlankLines(text) {
    if (!text) return "";
    const lines = text.split("\n");
    while (lines.length > 0 && lines[lines.length - 1].trim() === "") {
        lines.pop();
    }
    return lines.join("\n");
}
