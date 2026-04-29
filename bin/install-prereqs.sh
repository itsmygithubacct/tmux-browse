#!/usr/bin/env bash
# Install tmux-browse's external prerequisites.
#
# Runtime (always installed): tmux + ttyd.
# Dev tools (with --dev): ImageMagick + librsvg renderer, used by
#   bin/generate-pwa-icons.sh to rebuild the PWA icons from
#   static/favicon.svg. Only needed if you're contributing changes
#   that affect the icons; the PNGs themselves are checked into
#   the repo.
#
# Detects the host package manager (apt / dnf / yum / pacman / zypper /
# apk / brew / port / pkg). ttyd is fetched from upstream via
# tmux_browse.py install-ttyd because it isn't packaged on every
# distro and the bundled installer always works.
#
# Idempotent: re-running after partial success skips what's already
# installed. The script never sudos silently — it prints every command
# it's about to run, then runs it.
#
# Usage:
#   bin/install-prereqs.sh            # runtime only
#   bin/install-prereqs.sh --dev      # also install icon-regen tools

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
err() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; }

run() {
    printf '    \033[2m$ %s\033[0m\n' "$*"
    "$@"
}

need_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        return 1
    fi
    return 0
}

install_with() {
    local manager="$1"; shift
    local sudo_cmd=""
    if need_sudo && [ "$manager" != "brew" ]; then
        sudo_cmd="sudo"
    fi
    case "$manager" in
        apt)    run $sudo_cmd apt-get update -qq
                run $sudo_cmd apt-get install -y "$@" ;;
        dnf)    run $sudo_cmd dnf install -y "$@" ;;
        yum)    run $sudo_cmd yum install -y "$@" ;;
        pacman) run $sudo_cmd pacman -S --needed --noconfirm "$@" ;;
        zypper) run $sudo_cmd zypper -n install "$@" ;;
        apk)    run $sudo_cmd apk add "$@" ;;
        brew)   run brew install "$@" ;;
        port)   run $sudo_cmd port install "$@" ;;
        pkg)    run $sudo_cmd pkg install -y "$@" ;;
        *)      err "unsupported package manager: $manager"; return 1 ;;
    esac
}

detect_manager() {
    if [ "$(uname -s)" = "Darwin" ]; then
        for tool in brew port; do
            if command -v "$tool" >/dev/null 2>&1; then
                echo "$tool"; return
            fi
        done
    fi
    for tool in apt dnf yum pacman zypper apk pkg; do
        if command -v "$tool" >/dev/null 2>&1; then
            echo "$tool"; return
        fi
    done
    return 1
}

install_tmux() {
    if command -v tmux >/dev/null 2>&1; then
        say "tmux already installed: $(tmux -V)"
        return
    fi
    local manager
    if ! manager="$(detect_manager)"; then
        err "no recognised package manager on \$PATH"
        err "install tmux manually, then re-run this script."
        return 1
    fi
    say "installing tmux via $manager"
    install_with "$manager" tmux
}

install_ttyd() {
    if command -v ttyd >/dev/null 2>&1; then
        say "ttyd already installed: $(ttyd --version 2>&1 | head -1)"
        return
    fi
    if [ -x "$HOME/.local/bin/ttyd" ]; then
        say "ttyd already installed at ~/.local/bin/ttyd"
        return
    fi
    say "installing ttyd via the bundled installer"
    run python3 "$REPO_DIR/tmux_browse.py" install-ttyd
}

install_dev_tools() {
    # ImageMagick + an SVG renderer, only needed for re-rasterising
    # bin/generate-pwa-icons.sh. Package names vary slightly by manager.
    local manager
    if ! manager="$(detect_manager)"; then
        err "no recognised package manager on \$PATH (skipping --dev)"
        return 0
    fi
    if command -v convert >/dev/null 2>&1 && command -v rsvg-convert >/dev/null 2>&1; then
        say "dev tools already installed (ImageMagick + rsvg-convert)"
        return
    fi
    say "installing dev tools (ImageMagick + librsvg) via $manager"
    case "$manager" in
        apt)    install_with apt imagemagick librsvg2-bin ;;
        dnf)    install_with dnf ImageMagick librsvg2-tools ;;
        yum)    install_with yum ImageMagick librsvg2-tools ;;
        pacman) install_with pacman imagemagick librsvg ;;
        zypper) install_with zypper ImageMagick rsvg-view ;;
        apk)    install_with apk imagemagick librsvg ;;
        brew)   install_with brew imagemagick librsvg ;;
        port)   install_with port ImageMagick librsvg ;;
        pkg)    install_with pkg ImageMagick7 librsvg2 ;;
    esac
}

main() {
    say "tmux-browse prerequisite installer"
    install_tmux
    install_ttyd
    if [ "${1:-}" = "--dev" ]; then
        install_dev_tools
    fi
    echo
    say "verifying"
    python3 "$REPO_DIR/tmux_browse.py" doctor
}

main "$@"
