# Thin Makefile for shell-driven extension management.
#
# The dashboard's Config > Extensions card is the primary UX; these
# targets exist for headless hosts, Docker builds, bootstrap scripts,
# and anyone who prefers the CLI. Both routes go through the same
# ``lib.extensions`` functions — no duplicate logic.

.PHONY: help list-extensions \
        install-agent update-agent enable-agent disable-agent \
        uninstall-agent uninstall-agent-with-state test

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
	@echo "  make list-extensions           show status of every known extension"
	@echo "  make test                      run the core test suite"
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

test:
	$(PY) -m unittest discover tests
