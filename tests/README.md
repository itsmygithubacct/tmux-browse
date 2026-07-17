# tests

Stdlib `unittest` — matches the project's "no pip deps" constraint.

```bash
# Run preflight plus core, dashboard, and extension suites
make ci

# Run only the dashboard suite, or a specific dashboard module
make test
python3 -m unittest tests.test_server_handler -v
```

The CI target covers four layers:

- **Preflight**: core and extension tag/manifest compatibility.
- **Vendored core**: the complete `tmux-cli` unit suite.
- **Dashboard**: server, routes, configuration, streaming, tasks, templates,
  wrappers, and security regression tests.
- **Extensions**: every populated `extensions/*/tests` directory, with all
  extension roots importable so cross-extension integrations are exercised.

The suites mock destructive process operations; CI installs tmux so command
shape and server-detection behavior can also be exercised consistently.
