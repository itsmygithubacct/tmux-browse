#!/usr/bin/env bash
# Update an installed tmux-browse checkout to the latest release (or a
# specific ref), advance its initialised extension submodules to the
# refs the new core pins, verify prerequisites, and — when asked —
# restart a running dashboard so it picks up the new code.
#
# This is the counterpart to bin/quickstart_local.sh / quickstart_lan.sh:
# those clone + launch a fresh install, this advances an existing one in
# place. Both pick the "latest release" the same way (newest core
# vNNN.NNN.NNN tag), so an install bootstrapped by quickstart updates
# cleanly here.
#
# Usage:
#   bin/update.sh                 # update this checkout to the latest release
#   bin/update.sh --check         # report current vs latest, change nothing
#   bin/update.sh --ref v0.7.6.0  # update to a specific tag/ref
#   bin/update.sh --restart       # also restart a running local dashboard
#
# Options:
#   --dir <path>     checkout to update (default: this script's repo)
#   --ref <ref>      git ref to update to (default: latest core release tag)
#   --check          dry run: print current + target versions, then exit
#   --restart        after updating, ask a running dashboard to restart
#                    (POST /api/server/restart, picks up new code via re-exec)
#   --https          talk to the dashboard over https (self-signed ok) for --restart
#   --auth <token>   bearer token for --restart (or set TB_AUTH_TOKEN)
#   --auth-file <f>  read the bearer token from a file
#   --no-prereqs     skip the post-update `doctor` prerequisite check
#   --force          proceed even if the working tree has local changes
#                    (DISCARDS them: runs `git checkout -f`)
#   --help           show this and exit

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REF=""
CHECK=0
DO_RESTART=0
USE_HTTPS=0
AUTH_TOKEN="${TB_AUTH_TOKEN:-}"
AUTH_FILE=""
SKIP_PREREQS=0
FORCE=0

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarn:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//; s/^!.*//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        --ref) REF="$2"; shift 2 ;;
        --check) CHECK=1; shift ;;
        --restart) DO_RESTART=1; shift ;;
        --https) USE_HTTPS=1; shift ;;
        --auth) AUTH_TOKEN="$2"; shift 2 ;;
        --auth-file) AUTH_FILE="$2"; shift 2 ;;
        --no-prereqs) SKIP_PREREQS=1; shift ;;
        --force) FORCE=1; shift ;;
        --help|-h) usage ;;
        *) die "unknown flag: $1 (try --help)" ;;
    esac
done

need() { command -v "$1" >/dev/null 2>&1 || die "missing '$1' on PATH — install it and retry"; }
need git
need python3

INSTALL_DIR="$(cd "$INSTALL_DIR" 2>/dev/null && pwd || true)"
[[ -n "$INSTALL_DIR" && -d "$INSTALL_DIR/.git" ]] \
    || die "${INSTALL_DIR:-target} is not a git checkout — pass --dir <tmux-browse checkout>"
[[ -f "$INSTALL_DIR/tmux_browse.py" ]] \
    || die "$INSTALL_DIR doesn't look like a tmux-browse checkout (no tmux_browse.py)"

g() { git -C "$INSTALL_DIR" "$@"; }

# --- current version -------------------------------------------------------
# __version__ is the single source of truth and is readable regardless of
# git state (shallow clone, detached HEAD, etc.); git describe is a nicety.
current_version() { python3 -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); from lib import __version__; print(__version__)"; }
CUR_VER="$(current_version 2>/dev/null || echo '?')"
CUR_REF="$(g describe --tags --always 2>/dev/null || echo '?')"

# --- pick target ref -------------------------------------------------------
say "Fetching tags from origin..."
g fetch --tags --force --prune origin >/dev/null 2>&1 || warn "git fetch reported errors; using what's local"

if [[ -z "$REF" ]]; then
    # Newest core release tag (vNNN.NNN.NNN[.N]); extension tags like
    # v0.7.3-agent sort alongside but are filtered out. Mirrors the
    # detection in bin/quickstart_local.sh so both agree on "latest".
    REF="$(g tag -l --sort=-v:refname \
        | grep -E '^v[0-9]+\.[0-9]+(\.[0-9]+){1,2}$' \
        | head -n1 || true)"
    [[ -n "$REF" ]] || die "could not detect a release tag locally; pass --ref explicitly"
fi

# Resolve the target ref to a version string for display (read lib/__init__.py
# at that ref without checking it out).
target_version() {
    g show "$REF:lib/__init__.py" 2>/dev/null \
        | sed -n 's/^__version__ *= *"\(.*\)"/\1/p' | head -n1
}
TGT_VER="$(target_version || true)"; TGT_VER="${TGT_VER:-?}"

say "Current: $CUR_VER ($CUR_REF)"
say "Target:  $TGT_VER ($REF)"

# --- already current? ------------------------------------------------------
TGT_REV="$(g rev-parse --verify --quiet "${REF}^{commit}" 2>/dev/null || true)"
HEAD_REV="$(g rev-parse --verify HEAD 2>/dev/null || true)"
if [[ -n "$TGT_REV" && "$TGT_REV" == "$HEAD_REV" ]]; then
    say "Already at $REF — nothing to update."
    [[ "$CHECK" -eq 1 ]] && exit 0
    # Still refresh submodules in case an extension drifted; harmless no-op
    # when they're already aligned.
    g submodule update --recursive >/dev/null 2>&1 || true
    exit 0
fi

if [[ "$CHECK" -eq 1 ]]; then
    say "Update available: $CUR_VER → $TGT_VER  (run without --check to apply)"
    exit 0
fi

# --- guard the working tree ------------------------------------------------
if [[ -n "$(g status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        warn "working tree has local changes — discarding them (--force)"
    else
        err "working tree at $INSTALL_DIR has uncommitted changes."
        err "commit/stash them, or re-run with --force to discard and update."
        exit 1
    fi
fi

# --- check out the target --------------------------------------------------
say "Updating $INSTALL_DIR → $REF"
co_flags=(--quiet)
[[ "$FORCE" -eq 1 ]] && co_flags=(--quiet --force)
if ! g checkout "${co_flags[@]}" "$REF" 2>/dev/null; then
    # Shallow clones (what quickstart creates) often lack the target commit's
    # objects. Deepen once and retry before giving up.
    if [[ "$(g rev-parse --is-shallow-repository 2>/dev/null)" == "true" ]]; then
        say "Shallow checkout — fetching full history to reach $REF"
        g fetch --tags --force --unshallow origin >/dev/null 2>&1 \
            || g fetch --tags --force origin >/dev/null 2>&1 || true
        g checkout "${co_flags[@]}" "$REF" || die "checkout of $REF failed"
    else
        die "checkout of $REF failed (does the ref exist?)"
    fi
fi

# --- advance extensions ----------------------------------------------------
# Only touches already-initialised submodules; extensions are opt-in, so we
# never auto-init ones the operator hasn't installed. This moves installed
# extensions to the refs the new core pins in .gitmodules / the catalog.
if [[ -f "$INSTALL_DIR/.gitmodules" ]]; then
    say "Advancing installed extensions to their pinned refs"
    g submodule update --recursive >/dev/null 2>&1 \
        || warn "some submodules failed to update — check 'git -C $INSTALL_DIR submodule status'"
fi

NEW_VER="$(current_version 2>/dev/null || echo '?')"
say "Now on $NEW_VER ($(g describe --tags --always 2>/dev/null || echo "$REF"))"

# --- verify prerequisites --------------------------------------------------
if [[ "$SKIP_PREREQS" -eq 0 ]]; then
    say "Checking prerequisites (tmux, ttyd)..."
    if ! python3 "$INSTALL_DIR/tmux_browse.py" doctor; then
        warn "prerequisites missing — run bin/install-prereqs.sh (the dashboard"
        warn "won't start until they're present)."
    fi
fi

# --- restart a running dashboard ------------------------------------------
DASH_JSON="$HOME/.tmux-browse/dashboard.json"
restart_hint() {
    if [[ -f "$DASH_JSON" ]]; then
        python3 - "$DASH_JSON" <<'PY' 2>/dev/null || true
import json, os, sys
try:
    d = json.load(open(sys.argv[1]))
    pid, bind, port = d.get("pid"), d.get("bind", "127.0.0.1"), d.get("port", 8096)
    alive = False
    try:
        os.kill(int(pid), 0); alive = True
    except Exception:
        pass
    if alive:
        print(f"    a dashboard is running (pid {pid}) on {bind}:{port}.")
        print(f"    restart it to load the new code, e.g.:")
        print(f"      python3 tmux_browse.py serve --port {port} --bind {bind}")
        print(f"    or use this script's --restart flag.")
except Exception:
    pass
PY
    fi
}

dash_endpoint() {
    [[ -f "$DASH_JSON" ]] || return 1
    python3 - "$DASH_JSON" "$USE_HTTPS" <<'PY'
import json, os, sys
try:
    d = json.load(open(sys.argv[1]))
    pid = d.get("pid");
    try: os.kill(int(pid), 0)
    except Exception: sys.exit(1)
    bind = d.get("bind") or "127.0.0.1"
    host = "127.0.0.1" if bind in ("0.0.0.0", "", "::") else bind
    port = d.get("port", 8096)
    scheme = "https" if sys.argv[2] == "1" else "http"
    print(f"{scheme}://{host}:{port}/api/server/restart")
except Exception:
    sys.exit(1)
PY
}

if [[ "$DO_RESTART" -eq 1 ]]; then
    need curl
    [[ -z "$AUTH_TOKEN" && -n "$AUTH_FILE" ]] && AUTH_TOKEN="$(tr -d '\r\n' < "$AUTH_FILE" 2>/dev/null || true)"
    if URL="$(dash_endpoint)"; then
        say "Restarting dashboard via $URL"
        curl_args=(-fsS -X POST -m 10)
        [[ "$USE_HTTPS" -eq 1 ]] && curl_args+=(-k)
        [[ -n "$AUTH_TOKEN" ]] && curl_args+=(-H "Authorization: Bearer $AUTH_TOKEN")
        if curl "${curl_args[@]}" "$URL" -o /dev/null; then
            say "Restart requested — the dashboard is re-execing on $NEW_VER."
        else
            warn "restart request failed (auth? wrong scheme? try --https / --auth)."
            restart_hint
        fi
    else
        warn "no running dashboard found in $DASH_JSON — nothing to restart."
    fi
else
    restart_hint
fi

say "Update complete: $CUR_VER → $NEW_VER"
