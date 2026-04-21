#!/bin/bash
# Attach-only wrapper for ttyd. Does NOT create sessions — the dashboard
# owns the creation flow. Exits cleanly when the WebSocket drops (tty gone)
# so stale wrappers don't accumulate as orphaned tmux clients.
# Usage: ttyd_wrap.sh <session_name>

SESSION="${1:?Usage: ttyd_wrap.sh <session_name>}"

tty_alive() {
    [ -t 0 ] && [ -t 1 ]
}

while tty_alive; do
    # "=NAME" forces exact-match so prefix ambiguity can't attach to the
    # wrong session (tmux-browse's python side uses = everywhere).
    if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
        echo "[tmux-browse] session '$SESSION' is gone" >&2
        exit 0
    fi
    tmux attach-session -t "=$SESSION"
    sleep 1
done
