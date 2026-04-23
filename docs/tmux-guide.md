# How to Use tmux

tmux is a terminal multiplexer: it lets you run multiple terminal sessions
inside a single window, detach from them, and reattach later. Your programs
keep running in the background even when you close your terminal or lose
your connection.

## Core Concepts

**Sessions** are the top-level container. Each session is an independent
workspace with its own windows. You can detach from a session and
reattach later — everything inside keeps running.

**Windows** are like browser tabs inside a session. Each window fills the
terminal and can be switched between instantly.

**Panes** split a window into multiple visible terminals. You can have 2,
3, 4, or more panes showing different things simultaneously.

## Getting Started

```bash
# Create a new session named "work"
tmux new-session -s work

# In another terminal, attach to it
tmux attach -t work

# List all sessions
tmux ls

# Kill a session
tmux kill-session -t work
```

Once inside tmux, all commands start with the **prefix key**: `Ctrl+B`.
Press `Ctrl+B`, release it, then press the command key.

## Essential Keybindings

### Sessions

| Keys | Action |
|---|---|
| `Prefix d` | Detach (session keeps running) |
| `Prefix s` | List sessions and switch |
| `Prefix $` | Rename current session |
| `Prefix (` / `)` | Previous / next session |

### Windows

| Keys | Action |
|---|---|
| `Prefix c` | Create new window |
| `Prefix n` / `p` | Next / previous window |
| `Prefix 0-9` | Switch to window by number |
| `Prefix w` | Choose window from list |
| `Prefix ,` | Rename current window |
| `Prefix &` | Close window (confirms) |
| `Prefix l` | Toggle to last window |

### Panes

| Keys | Action |
|---|---|
| `Prefix "` | Split top/bottom |
| `Prefix %` | Split left/right |
| `Prefix Arrow` | Move between panes |
| `Prefix z` | Zoom pane (toggle fullscreen) |
| `Prefix x` | Close pane (confirms) |
| `Prefix !` | Break pane into its own window |
| `Prefix Space` | Cycle through layouts |
| `Prefix q` | Show pane numbers briefly |

### Resizing Panes

| Keys | Action |
|---|---|
| `Prefix Ctrl+Arrow` | Resize by 1 line/column |
| `Prefix Alt+Arrow` | Resize by 5 lines/columns |

## Scrollback and Copy Mode

To scroll through terminal history or copy text:

1. **Enter copy mode**: `Prefix [`
2. **Scroll**: Arrow keys, Page Up/Down, or mouse wheel
3. **Search**: `Ctrl+R` (backward) or `Ctrl+S` (forward)
4. **Select text**: press `Space` to start, navigate to end
5. **Copy**: press `Enter` (copies and exits copy mode)
6. **Paste**: `Prefix ]`

### Copy Mode Navigation

| Keys | Action |
|---|---|
| Arrow keys | Move cursor |
| `Page Up` / `Page Down` | Scroll by page |
| `Ctrl+R` | Search backward |
| `Ctrl+S` | Search forward |
| `n` / `N` | Next / previous search result |
| `Space` | Start selection |
| `Enter` | Copy selection and exit |
| `q` or `Escape` | Exit without copying |

## Mouse Support

Mouse is off by default. To enable it:

```bash
# Inside tmux, press Prefix : then type:
set -g mouse on
```

With mouse enabled you can:
- Click to select panes
- Drag pane borders to resize
- Scroll with the mouse wheel (enters copy mode automatically)
- Select text by dragging (copies on release)
- Double-click to select a word
- Triple-click to select a line

## Common Workflows

### Working on Multiple Projects

```bash
tmux new -s project-a
# ... do work, then detach with Prefix d
tmux new -s project-b
# Switch between them with Prefix s
```

### Monitoring a Long-Running Process

1. Start the process in a pane
2. Split: `Prefix "` or `Prefix %`
3. Work in the new pane while watching the process
4. Zoom into the process pane: `Prefix z`
5. Zoom back out: `Prefix z` again

### Pair Programming / Multi-Device Access

Multiple people (or devices) can attach to the same session:

```bash
# Person 1
tmux new -s shared

# Person 2 (same machine or via SSH)
tmux attach -t shared
```

Both see and can type into the same panes.

### Searching Terminal History

1. `Prefix [` to enter copy mode
2. `Ctrl+R` and type your search term
3. `n` to find next match, `N` for previous
4. `q` to exit

### Quick Pane Layouts

| Keys | Layout |
|---|---|
| `Prefix Alt+1` | Even horizontal (side by side) |
| `Prefix Alt+2` | Even vertical (stacked) |
| `Prefix Alt+3` | Main horizontal (big top, small bottom) |
| `Prefix Alt+4` | Main vertical (big left, small right) |
| `Prefix Alt+5` | Tiled (equal grid) |

## The Command Prompt

`Prefix :` opens a command prompt where you can type any tmux command:

```
new-window -n builds
split-window -h -p 30
resize-pane -U 10
set -g mouse on
kill-pane -t 2
```

## Tips

- **Detach, don't close.** `Prefix d` keeps everything running. Closing
  the terminal kills the client but not the session.
- **Name your sessions.** `tmux new -s name` is easier to find later than
  session 0, 1, 2.
- **Zoom is your friend.** `Prefix z` makes a pane fullscreen temporarily
  without changing the layout.
- **Prefix ?** shows all keybindings if you forget something.
- **History limit** defaults to 2000 lines. Increase it with
  `set -g history-limit 50000` for more scrollback.
