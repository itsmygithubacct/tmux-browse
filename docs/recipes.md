# Recipes

Short, concrete examples for `tb` and the dashboard. Each recipe is
self-contained — paste it into a terminal, swap the session names for your
own.

## Human recipes

### "Run this line, wait for the prompt, show me the output"

```bash
tb type work "make build"
tb wait work --idle 2 --timeout 120
tb capture work -n 100 | tail -50
```

Or condensed:

```bash
tb exec work --timeout 120 -- make build
```

### Fire-and-forget a long job

```bash
tb type builds "./long_task.sh &"
# come back later
tb capture builds -n 200
```

### Watch a log in one pane from another pane

```bash
tb watch logs
```

Prints timestamped events whenever the `logs` session's pane changes.
Ctrl-C to stop.

### Re-enter a session's scrollback from the dashboard

In the dashboard's summary row, click **Scroll** (equivalent to `C-b [`).
Page up/down with your keyboard inside the ttyd iframe. Press `q` or
`Escape` to leave copy-mode.

### Quickly open every attached session in its own browser tab

```bash
for s in $(tb ls --attached --no-header --json | jq -r '.data[].name'); do
    tb web start "$s" | xargs -I{} xdg-open "{}"
done
```

(Replace `xdg-open` with `open` on macOS.)

### Stop every ttyd without killing tmux

```bash
tmux-browse cleanup
```

### Rename a session and keep its port assignment

`ports.json` is keyed by name, so a rename effectively abandons the old
port. If you care about URL stability, avoid renaming. If you've renamed,
run `tmux-browse ports --prune` afterwards to drop the stale entry.

## LLM agent recipes

The pattern in one sentence: **`snapshot` once, then loop `exec` + `wait`
/ `watch`, finishing with `capture` or `describe` for context.**

### Minimal tool schema

Expose a small set of verbs to the model:

```
tb snapshot                → JSON of every session and pane
tb exec <target> --json -- <cmd>  → run and capture
tb type <target> "<line>"
tb key  <target> <Key>...
tb capture <target> -n N   → last N lines
tb wait <target> --idle 2 --timeout 60
tb new  --auto             → create a fresh workspace
tb kill <target> -f        → clean up
```

Everything else (attach, rename, web) is optional.

### Run a command and branch on exit status

```bash
RESULT=$(tb exec build --json --timeout 300 -- "make test")
EXIT=$(echo "$RESULT" | jq -r .data.exit_status)
if [ "$EXIT" = "0" ]; then
    echo "tests passed"
else
    echo "$RESULT" | jq -r .data.output | tail -40
fi
```

In an agent: the JSON is all the agent needs — `ok`, `exit_status`, and
`output` for reasoning.

### Detect a long-running process and leave it alone

```bash
# First: is anything running in this pane?
CURRENT=$(tb show work --json | jq -r '.data.panes[0].command')
if [ "$CURRENT" = "bash" ]; then
    tb exec work --timeout 5 -- ls
else
    echo "pane is running '$CURRENT'; not interrupting"
fi
```

### Poll until a file appears, then do something

```bash
until tb exec work --json --timeout 5 -- "test -f /tmp/DONE" \
      | jq -e '.data.exit_status == 0' >/dev/null; do
    sleep 2
done
tb exec work --timeout 5 -- "cat /tmp/DONE"
```

### Start a scratch session, run a pipeline, kill it

```bash
NAME=$(tb new --auto --cwd "$PWD")
tb exec "$NAME" --timeout 10 -- "python -m venv .venv && source .venv/bin/activate && pip install -q requests"
tb exec "$NAME" --timeout 30 --json -- "python my_script.py" > result.json
tb kill "$NAME" -f
```

### Drive a REPL without a shell underneath

For non-shell panes, `exec` falls back to the **idle** strategy
automatically (`exit_status` will be `null`, but the captured output is
returned when the REPL stops producing output). Or drive the REPL
yourself:

```bash
tb type repl "help(len)"
tb wait repl --idle 1 --timeout 10
tb capture repl -n 40
```

### Ralph loop (re-read a prompt file every iteration)

Combining `send`/`type` with `watch` and a file you keep editing gives you
the "Ralph" loop pattern — an LLM driven by a prompt you continually
refine:

```bash
# Terminal 1 — the agent's work session
tb new ralph --cmd "claude --dangerously-skip-permissions"

# Terminal 2 — edit the prompt
${EDITOR:-vim} PROMPT.md

# Terminal 3 — drive it
while true; do
    tb paste ralph < PROMPT.md
    tb wait ralph --idle 5 --timeout 600
    sleep 10
done
```

(This is the pattern Geoff Huntley calls a "Ralph" loop. Stop when it
satisfies the prompt, or when you kill the loop.)

### Snapshot as agent context

Prime an agent's context with one fetch:

```bash
tb snapshot > /tmp/ctx.json
```

The snapshot is self-describing — the model can see every session, every
pane, every running ttyd, and the dashboard's port — so it can answer
"what sessions are idle, and which one is the build?" without further
round-trips.

### Prefer `tb exists` for existence checks

Don't parse `ls` output — use the dedicated exit-code verb:

```bash
if tb exists work; then
    tb exec work -- ./deploy.sh
else
    tb new work --cwd ~/src/app
fi
```

Exit 0 → exists; exit 3 → doesn't. No output, no parsing.

## Dashboard recipes

### Reserve a stable URL for a long-lived session

Port assignments in `~/.tmux-browse/ports.json` are permanent. Create the
session, expand its pane once in the dashboard (this allocates + starts
ttyd on its port), then bookmark the ttyd URL. That URL will work for as
long as the session exists — and `tb web start <name>` re-attaches to the
same port after restarts.

### Running on multiple machines

Each host runs its own `tmux_browse.py serve`. Dashboards don't talk to
each other. Bookmark one URL per host:

```
http://laptop.local:8096/
http://workstation.local:8096/
http://build-box.local:8096/
```

Each has its own `~/.tmux-browse/ports.json`; the port `7700` will map to
a **different** session on each host — that's intentional.

### Hide/unhide sessions you don't want cluttering the main list

Click **Hide** in the summary row. The pane moves to the **Hidden (N)**
section at the bottom. Hidden state is per-browser (localStorage) and
per-machine — not shared across devices.
