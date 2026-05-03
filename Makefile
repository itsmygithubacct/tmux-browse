# Thin Makefile for shell-driven extension management.
#
# The dashboard's Config > Extensions card is the primary UX; these
# targets exist for headless hosts, Docker builds, bootstrap scripts,
# and anyone who prefers the CLI. Both routes go through the same
# ``lib.extensions`` functions — no duplicate logic.

.PHONY: help list-extensions \
        install-agent update-agent enable-agent disable-agent \
        uninstall-agent uninstall-agent-with-state \
        install-federation update-federation enable-federation disable-federation \
        uninstall-federation uninstall-federation-with-state \
        preflight test ci

PY ?= python3

help:
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
	@echo "  make test                      run the core test suite"
	@echo "  make ci                        preflight + tests (what CI runs)"
	@echo ""
	@echo "After install/update/enable/disable, restart the dashboard."

list-extensions:
	$(PY) -m lib.extensions list

install-agent:
	$(PY) -m lib.extensions install agent

update-agent:
	$(PY) -m lib.extensions update agent

enable-agent:
	$(PY) -m lib.extensions enable agent

disable-agent:
	$(PY) -m lib.extensions disable agent

uninstall-agent:
	$(PY) -m lib.extensions uninstall agent

uninstall-agent-with-state:
	$(PY) -m lib.extensions uninstall agent --remove-state

install-federation:
	$(PY) -m lib.extensions install federation

update-federation:
	$(PY) -m lib.extensions update federation

enable-federation:
	$(PY) -m lib.extensions enable federation

disable-federation:
	$(PY) -m lib.extensions disable federation

uninstall-federation:
	$(PY) -m lib.extensions uninstall federation

uninstall-federation-with-state:
	$(PY) -m lib.extensions uninstall federation --remove-state

preflight:
	$(PY) scripts/preflight.py

test:
	$(PY) -m unittest discover tests

ci: preflight test
