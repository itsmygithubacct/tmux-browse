# Thin Makefile for shell-driven extension management.
#
# The dashboard's Config > Extensions card is the primary UX; these
# targets exist for headless hosts, Docker builds, bootstrap scripts,
# and anyone who prefers the CLI. Both routes go through the same
# ``lib.extensions`` functions — no duplicate logic.
#
# The `tb` CLI core ships as the `tmux-cli` git submodule. Everything that
# imports `lib` runs with the submodule on PYTHONPATH (so the `lib` namespace
# package merges core + dashboard) and TB_PROJECT_DIR pointed at this checkout
# (so extensions/ + .gitmodules here, not in the vendored core, are the root).

.PHONY: help init update list-extensions \
        install-agent update-agent enable-agent disable-agent \
        uninstall-agent uninstall-agent-with-state \
        install-federation update-federation enable-federation disable-federation \
        uninstall-federation uninstall-federation-with-state \
        preflight test-core test test-extensions ci clean

PY ?= python3
RUN := PYTHONPATH=tmux-cli TB_PROJECT_DIR=$(CURDIR) $(PY)

help:
	@echo "tmux-browse maintenance targets:"
	@echo ""
	@echo "  make init                      pull the tmux-cli submodule (git submodule update --init --recursive)"
	@echo "  make update                    update this checkout to the latest release"
	@echo ""
	@echo "tmux-browse extension management targets:"
	@echo ""
	@echo "  make install-agent             clone/init + enable the agent extension"
	@echo "  make update-agent              advance the agent to its pinned ref"
	@echo "  make enable-agent              flip enabled=true (restart to activate)"
	@echo "  make disable-agent             flip enabled=false (keeps code)"
	@echo "  make uninstall-agent           remove the agent code (keeps state)"
	@echo "  make uninstall-agent-with-state  also delete ~/.tmux-browse/agent-*"
	@echo ""
	@echo "  make install-federation        clone/init + enable the federation extension"
	@echo "  make update-federation         advance federation to its pinned ref"
	@echo "  make enable-federation         flip enabled=true (restart to activate)"
	@echo "  make disable-federation        flip enabled=false (keeps code)"
	@echo "  make uninstall-federation      remove federation code (keeps paired-peers)"
	@echo "  make uninstall-federation-with-state  also delete ~/.tmux-browse/paired-peers.json"
	@echo ""
	@echo "  make list-extensions           show status of every known extension"
	@echo "  make preflight                 check core/extension version alignment"
	@echo "  make test-core                 run the vendored tmux-cli test suite"
	@echo "  make test                      run the dashboard test suite"
	@echo "  make test-extensions           run every populated extension test suite"
	@echo "  make ci                        run preflight + all test layers"
	@echo "  make clean                     remove __pycache__, *.pyc, .pytest_cache"
	@echo ""
	@echo "After install/update/enable/disable, restart the dashboard."

# Pull (or refresh) the vendored tb CLI core.
init:
	git submodule update --init --recursive

# Update this checkout to the latest release (delegates to bin/update.sh).
# Pass flags through with ARGS, e.g.  make update ARGS="--restart"  or
# make update ARGS="--ref v0.7.6.0 --check".
update:
	bash bin/update.sh $(ARGS)

list-extensions:
	$(RUN) -m lib.extensions list

install-agent:
	$(RUN) -m lib.extensions install agent

update-agent:
	$(RUN) -m lib.extensions update agent

enable-agent:
	$(RUN) -m lib.extensions enable agent

disable-agent:
	$(RUN) -m lib.extensions disable agent

uninstall-agent:
	$(RUN) -m lib.extensions uninstall agent

uninstall-agent-with-state:
	$(RUN) -m lib.extensions uninstall agent --remove-state

install-federation:
	$(RUN) -m lib.extensions install federation

update-federation:
	$(RUN) -m lib.extensions update federation

enable-federation:
	$(RUN) -m lib.extensions enable federation

disable-federation:
	$(RUN) -m lib.extensions disable federation

uninstall-federation:
	$(RUN) -m lib.extensions uninstall federation

uninstall-federation-with-state:
	$(RUN) -m lib.extensions uninstall federation --remove-state

preflight:
	$(RUN) scripts/preflight.py

test-core:
	$(MAKE) -C tmux-cli test PY=$(PY)

test:
	$(RUN) -m unittest discover tests

test-extensions:
	@set -e; \
	ext_path="$$($(PY) -c 'from pathlib import Path; print(":".join(str(p) for p in sorted(Path("extensions").iterdir()) if p.is_dir()))')"; \
	for test_dir in extensions/*/tests; do \
		[ -d "$$test_dir" ] || continue; \
		echo "== $$test_dir =="; \
		PYTHONPATH="tmux-cli:$$ext_path" TB_PROJECT_DIR="$(CURDIR)" \
			$(PY) -m unittest discover "$$test_dir"; \
	done

ci: preflight test-core test test-extensions

# Remove Python bytecode caches and the pytest cache. Safe to run any
# time; everything it deletes is regenerated on the next run.
clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache
