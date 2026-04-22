# tests

Stdlib `unittest` — matches the project's "no pip deps" constraint.

```bash
# Run the suite
python3 -m unittest discover -s tests -v

# Or a specific module
python3 -m unittest tests.test_targeting -v
```

These cover the logic that doesn't depend on tmux / ttyd / subprocess I/O.
Subprocess-heavy code (`lib/sessions.py`, `lib/ttyd.py` spawn paths) is
intentionally out of scope — integration tests for those need a live tmux
server and are better run in CI with `make test-integration` once someone
adds that.
