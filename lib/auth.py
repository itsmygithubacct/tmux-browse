"""Optional bearer-token auth for the dashboard.

**Default: no auth** (backward compatible). Opt in via CLI / env:

    tmux-browse serve --auth s3cr3t              # literal token
    tmux-browse serve --auth-file ~/.tb_token    # token read from file
    TMUX_BROWSE_TOKEN=s3cr3t tmux-browse serve   # env var

When enabled, every HTTP endpoint requires one of:

    Authorization: Bearer <token>     (preferred; API use)
    Cookie: tb_auth=<token>           (browser use after bootstrap)
    GET /?token=<token>               (one-time bootstrap — sets the cookie
                                       and 302-redirects to /)

The ``/health`` endpoint remains open so monitoring still works.

**Caveat:** this guards the dashboard HTTP surface only. The per-session
ttyd processes spawned by the dashboard run on their own ports (7700-7799)
and are NOT protected by this token. If you need authenticated terminals,
put the whole stack behind a reverse proxy that terminates TLS and
authenticates there, or bind the dashboard + ttyds to ``127.0.0.1`` and
tunnel in over SSH.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .errors import StateError

COOKIE_NAME = "tb_auth"
OPEN_PATHS = {"/health", "/favicon.ico", "/favicon.svg"}  # paths that skip the auth check


def load_token(cli_token: str | None = None,
               cli_token_file: str | None = None) -> str | None:
    """Resolve the configured token, or None if auth is disabled.

    Priority: ``--auth`` > ``--auth-file`` > ``TMUX_BROWSE_TOKEN`` env var.
    An empty / whitespace-only value disables auth.
    """
    def clean(v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    if cli_token is not None:
        return clean(cli_token)
    if cli_token_file:
        try:
            for line in Path(cli_token_file).read_text().splitlines():
                token = clean(line)
                if token is not None:
                    return token
            return None
        except OSError as e:
            raise StateError(f"cannot read auth file {cli_token_file}: {e}")
    return clean(os.environ.get("TMUX_BROWSE_TOKEN"))


def extract_token(handler) -> str | None:
    """Pull a token from Authorization header, cookie, or query string."""
    auth = handler.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None

    cookie_header = handler.headers.get("Cookie", "")
    if cookie_header:
        jar = SimpleCookie()
        try:
            jar.load(cookie_header)
        except Exception:
            pass
        if COOKIE_NAME in jar:
            return jar[COOKIE_NAME].value or None

    query = urlparse(handler.path).query
    if query:
        params = parse_qs(query)
        vals = params.get("token")
        if vals:
            return vals[0]
    return None


def matches(expected: str, given: str | None) -> bool:
    """Constant-time token compare."""
    if not given:
        return False
    return hmac.compare_digest(expected, given)


def path_is_open(path: str) -> bool:
    # Accept trailing slashes, query strings, etc.
    parsed = urlparse(path).path
    return parsed in OPEN_PATHS


def send_401(handler, *, reason: str = "authentication required") -> None:
    payload = json.dumps({
        "ok": False, "error": reason, "code": "EAUTH", "exit": 9,
    }) + "\n"
    body = payload.encode("utf-8")
    handler.send_response(401)
    handler.send_header("WWW-Authenticate", 'Bearer realm="tmux-browse"')
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_cookie_header(token: str, *, max_age: int = 7 * 24 * 3600) -> str:
    """Build a Set-Cookie value. HttpOnly + Lax by default."""
    return (
        f"{COOKIE_NAME}={token}; Path=/; HttpOnly; "
        f"SameSite=Lax; Max-Age={max_age}"
    )


def suggest_token() -> str:
    """Return a fresh random token for --help / docs examples."""
    return secrets.token_urlsafe(24)
