# tests

Stdlib `unittest` — matches the project's "no pip deps" constraint.

```bash
# Run the suite
python3 -m unittest discover -s tests -v

# Or a specific module
python3 -m unittest tests.test_targeting -v
```

304 tests across 22 files covering:

- **Core logic**: targeting, output formatting, port registry (incl.
  corrupt-registry recovery), atomic PID writes, filename round-trips,
  interface-cache/ifconfig parsing
- **Agent runtime**: provider dispatch and response parsing, runner JSON
  extraction and lifecycle events, conversation CRUD and forking,
  runtime session management, log persistence and latest-entry reads,
  run index append and filtered queries, cost recording and aggregation
- **Agent operations**: status derivation, scheduler tick logic and
  workflow execution, scheduler lock acquire/release/stale-PID handling,
  workflow run history and state tracking
- **Dashboard**: server route registration and agent endpoints, dashboard
  config normalization, agent store save/load/key-preservation
- **Tasks**: task CRUD, worktree slug generation

These cover the logic that doesn't depend on tmux / ttyd / subprocess I/O.
Subprocess-heavy code (`lib/sessions.py`, `lib/ttyd.py` spawn paths) is
intentionally out of scope — integration tests for those need a live tmux
server and are better run in CI with `make test-integration` once someone
adds that.
