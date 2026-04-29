# Remote-access recipes

The dashboard listens on `0.0.0.0:8096` by default — fine for the
single-LAN case, but you'll want one of these patterns when:

- You want to reach the dashboard from your phone over cellular.
- You want to bookmark it and have the URL stay stable across
  server restarts (so the home-screen PWA install survives).
- You want HTTPS without managing certs yourself.
- You want to share a tmux session with someone outside your
  network on a one-off basis.

All five recipes assume `tmux-browse serve` is already running
on the host. Pair every public-internet recipe with `--auth`
(see `docs/dashboard.md`) — none of these tunnels add
authentication on their own.

## 1. SSH tunnel — simplest, no extra software

The tightest option for a single user with SSH access to the
host. The dashboard never opens to the public internet.

```bash
# On your laptop
ssh -L 8096:localhost:8096 user@hostA

# Then in your browser
open http://localhost:8096/
```

`hostA` here is whatever `~/.ssh/config` host alias points at
the machine running `tmux-browse serve`. The `-L` forwards
your laptop's port 8096 to the remote host's loopback, so the
dashboard never needs to be reachable on any external interface
— pair with `tmux-browse serve --bind 127.0.0.1` to enforce
this server-side.

**Security:** SSH itself authenticates and encrypts the
forward. No additional auth needed on the dashboard for this
path.

## 2. Tailscale Funnel — preferred for permanent phone access

Funnel exposes a Tailscale node on a stable public HTTPS URL,
issues a real Let's Encrypt cert, and stays up across server
restarts. PWAs installed against this URL keep working.

```bash
# One-time tailnet setup (skip if already on Tailscale)
sudo tailscale up
# Funnel must be allowed on this node — set it from the admin
# console (Settings → Funnel) or with:
sudo tailscale set --funnel=true

# On the host running tmux-browse
TOKEN=$(openssl rand -hex 24)
tmux-browse serve --bind 127.0.0.1 --auth "$TOKEN" &
sudo tailscale funnel --bg --https=443 http://localhost:8096

# Print the public URL
tailscale funnel status
```

**If `tailscale funnel` errors with "Funnel is not enabled
for this tailnet":** the node doesn't have the `funnel`
capability in the tailnet's ACL. Edit the ACL in the admin
console and add `funnel` to `nodeAttrs` for the node's tags
(or to a group it belongs to). Re-run the funnel command.

**Security:** Funnel surfaces the dashboard publicly — anyone
with the URL can reach it. Always pair with `--auth` to gate
on a Bearer token, and consider keeping the URL private (it's
in `tailscale funnel status` and not enumerable).

## 3. Cloudflare quick tunnel — zero-config, rotating URL

For ad-hoc "show me what your tmux is doing" support sessions.
The URL changes every invocation; not for permanent
bookmarks.

```bash
# Install cloudflared once (Linux + macOS — see Cloudflare docs
# for full options)
brew install cloudflare/cloudflare/cloudflared
# or:  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared

# Each session
TOKEN=$(openssl rand -hex 24)
tmux-browse serve --bind 127.0.0.1 --auth "$TOKEN" &
cloudflared tunnel --url http://localhost:8096
```

`cloudflared` prints a `https://random-words-rotate.trycloudflare.com`
URL on stderr. Send it (and the token) to whoever needs
access; cancel the `cloudflared` process when you're done.

**Security:** quick tunnels rotate URLs on each run, which
limits exposure naturally. Still pair with `--auth`.

## 4. Cloudflare named tunnel — stable public URL with your DNS

Like Funnel, stable URL, but on Cloudflare's network and you
own the DNS record.

```bash
# One-time setup
cloudflared tunnel login
cloudflared tunnel create tmux-browse-tunnel
cloudflared tunnel route dns tmux-browse-tunnel tmux.example.com

# Each run
TOKEN=$(openssl rand -hex 24)
tmux-browse serve --bind 127.0.0.1 --auth "$TOKEN" &
cloudflared tunnel run --url http://localhost:8096 tmux-browse-tunnel
```

After this, `https://tmux.example.com/?token=$TOKEN` is the
stable URL. Cloudflare's edge handles TLS, so no certs to
manage on the host.

**Security:** same as Funnel — public URL gated only by your
auth token. Use a long token, rotate periodically.

## 5. Reverse proxy (nginx, Caddy) — when you already run one

If the host already terminates TLS for other services, just
add a proxy block. See
[`docs/dashboard.md`](dashboard.md#optional-tls-https) for the
existing notes; the dashboard works behind any HTTP proxy that
forwards `Upgrade` and `Connection: Upgrade` headers (so the
ttyd WebSocket survives).

Sketch (nginx):

```nginx
location / {
    proxy_pass http://127.0.0.1:8096;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

Don't forget the per-session ttyd ports (default 7700–7799) —
they need their own proxy stanzas, or a wildcard, because the
dashboard iframes connect directly to them.

**Security:** the proxy enforces TLS and (optionally) auth —
configure auth at the proxy layer if you'd rather not run with
`--auth`.

## See also

- [`docs/dashboard.md`](dashboard.md) — the dashboard's own
  auth + TLS options (Bearer token, BYO cert).
- The dashboard ships unauthenticated by default. None of the
  recipes above add auth on their own; always pair with
  `--auth`, an upstream proxy, or both.
