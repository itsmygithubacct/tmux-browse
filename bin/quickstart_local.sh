#!/usr/bin/env bash
# tmux-browse quickstart (localhost-only): clone the latest release,
# install prerequisites, and launch the dashboard server bound to
# 127.0.0.1. For LAN exposure use bin/quickstart_lan.sh instead.
#
# Usage from the internet:
#
#   curl -fsSL https://raw.githubusercontent.com/itsmygithubacct/tmux-browse/main/bin/quickstart_local.sh | bash
#
# Or with options (note the `bash -s --`):
#
#   curl -fsSL .../quickstart_local.sh | bash -s -- --dir ~/tb --port 8097
#
# Or locally:
#
#   bash bin/quickstart_local.sh --no-launch
#
# Options:
#   --dir <path>     install directory (default: ~/tmux-browse)
#   --port <n>       HTTP port (default: 8096)
#   --bind <addr>    bind address (default: 127.0.0.1)
#   --ref <tag>      git ref to check out (default: the latest release tag)
#   --no-prereqs     skip running bin/install-prereqs.sh
#   --no-launch      install only; don't start the server
#   --help           show this and exit

set -euo pipefail

REPO="https://github.com/itsmygithubacct/tmux-browse.git"
INSTALL_DIR="${HOME}/tmux-browse"
PORT="8096"
BIND="127.0.0.1"
REF=""
SKIP_PREREQS=0
NO_LAUNCH=0

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarn:\033[0m %s\n' "$*" >&2; }
err() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//; s/^!.*//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --bind) BIND="$2"; shift 2 ;;
        --ref) REF="$2"; shift 2 ;;
        --no-prereqs) SKIP_PREREQS=1; shift ;;
        --no-launch) NO_LAUNCH=1; shift ;;
        --help|-h) usage ;;
        *) die "unknown flag: $1 (try --help)" ;;
    esac
done

# --- prerequisite tools (required to even run this script) ----------------
need() { command -v "$1" >/dev/null 2>&1 || die "missing '$1' on PATH — install it and retry"; }
need git
need python3

# --- pick ref --------------------------------------------------------------
# `git ls-remote --tags --sort=-v:refname` returns tags newest-first, e.g.
#   ...
#   3ac5dda...   refs/tags/v0.7.4.1
#   80e1156...   refs/tags/v0.7.4.0
# Filter to vNNN.NNN.NNN-style core tags only — extension tags like
# v0.7.3-agent live alongside but aren't core release tags.
if [[ -z "$REF" ]]; then
    say "Looking up latest tmux-browse release tag..."
    REF="$(git ls-remote --tags --refs --sort=-v:refname "$REPO" 2>/dev/null \
        | awk '{print $2}' \
        | grep -E 'refs/tags/v[0-9]+\.[0-9]+(\.[0-9]+){1,2}$' \
        | sed 's|refs/tags/||' \
        | head -n1 || true)"
    [[ -n "$REF" ]] || die "could not detect a release tag from $REPO"
    say "Latest release: $REF"
fi

# --- clone or update -------------------------------------------------------
if [[ -d "$INSTALL_DIR/.git" ]]; then
    say "Updating existing checkout at $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --tags origin >/dev/null
    git -C "$INSTALL_DIR" checkout --quiet "$REF"
elif [[ -e "$INSTALL_DIR" ]] && [[ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]]; then
    die "$INSTALL_DIR exists and is not a tmux-browse checkout — refusing to overwrite"
else
    say "Cloning $REPO into $INSTALL_DIR (ref: $REF)"
    # Shallow clone keeps the download fast; full history isn't needed
    # to run the dashboard. Extensions stay un-fetched (opt-in).
    git clone --depth 1 --branch "$REF" "$REPO" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- prereqs ---------------------------------------------------------------
# Two checks: tmux on PATH, and ttyd reachable — either on PATH or via
# tmux_browse.py's bundled installer that drops a static binary in
# ~/.local/bin. We delegate to `tmux_browse.py doctor`; its exit code is
# 0 when all required prereqs are present, 8 when something is missing.
if [[ "$SKIP_PREREQS" -eq 0 ]]; then
    say "Checking prerequisites (tmux, ttyd)..."
    if python3 tmux_browse.py doctor >/dev/null 2>&1; then
        say "All prerequisites already present; skipping install"
    else
        # Re-run visibly so the operator sees what's missing.
        python3 tmux_browse.py doctor || true
        if [[ -x bin/install-prereqs.sh ]]; then
            say "Installing missing prerequisites via bin/install-prereqs.sh"
            bash bin/install-prereqs.sh \
                || warn "installer reported errors — continuing; re-run with --no-prereqs to skip"
        else
            warn "bin/install-prereqs.sh not found at this ref; cannot auto-install"
        fi
        # Re-check after install to confirm we're now green.
        if ! python3 tmux_browse.py doctor; then
            die "prerequisites still missing after install — see the doctor output above"
        fi
    fi
fi

# --- launch ----------------------------------------------------------------
if [[ "$NO_LAUNCH" -eq 1 ]]; then
    say "Install complete. To start the server:"
    printf '\n    cd %s && python3 tmux_browse.py serve --port %s --bind %s\n\n' \
        "$INSTALL_DIR" "$PORT" "$BIND"
    exit 0
fi

say "Starting the dashboard on http://${BIND}:${PORT}/"
exec python3 tmux_browse.py serve --port "$PORT" --bind "$BIND"
