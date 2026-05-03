# LAN federation

> **Status:** federation lives in the
> [`tmux-browse-federation`](https://github.com/itsmygithubacct/tmux-browse-federation)
> extension as of core 0.7.6.0. Install with `make install-federation`
> + `make enable-federation` from the core checkout, then restart
> the dashboard. The behavior described below is unchanged from the
> in-core version that shipped in 0.7.3 → 0.7.5; only the install
> path and the disable mechanism have changed (see
> [Disabling federation](#disabling-federation)).

When two or more tmux-browse instances run on the same broadcast
domain (a LAN segment), they auto-discover each other. After both
sides explicitly accept the pairing, their session lists merge in
each other's dashboard, with each remote session's name prefixed by
the originating peer's hostname (`hostA:work`).

This is intended for the "I have tmux-browse on my workstation and
on a Pi by the bench, both on my home network, I want one
dashboard" case — not for cross-internet aggregation, not for
shared networks.

## Two phases: discovery, then pairing

**Discovery (automatic).** Each instance broadcasts a tiny JSON
beacon to UDP `255.255.255.255:8095` every five seconds:

```json
{
  "device_id": "1c7d…",
  "hostname": "hostA",
  "dashboard_port": 8096,
  "scheme": "http",
  "version": "0.7.4.0",
  "beacon_seq": 42
}
```

The same instance also listens on UDP 8095. Each beacon it receives
lands in the in-memory peer registry with the source IP attached.
Peers expire 15 seconds after their last beacon (3× the cadence,
so a single dropped packet doesn't drop the peer).

Stdlib-only: socket plus a daemon thread for each direction. No
mDNS, no zeroconf, no central registry.

**Pairing (operator-initiated, both sides).** Discovery alone
does not aggregate sessions. Each side sees the other in the
**Federation** subsection of the Config pane (also at
`GET /api/peers`), with status `discovered`. Then:

1. Operator on hostA clicks **Request Pair** on hostB's row.
   hostA POSTs to `hostB/api/peers/pair-request`. hostB records the
   request and shows it in its own Federation card with **Accept**
   / **Decline** buttons. hostA's row flips to status
   `request-sent` (waiting).

2. Operator on hostB clicks **Accept**. hostB writes the pairing
   to its persistent store (`~/.tmux-browse/paired-peers.json`,
   mode 0600) AND POSTs to `hostA/api/peers/pair-accept-callback`.
   hostA writes the same pairing to its own store IFF it has an
   outgoing record for hostB (so a hostile peer can't unilaterally
   pair itself with you by sending an unsolicited "we accepted"
   message).

Now both hosts have each other in their paired set. The session
aggregation only fetches from peers that are both **discovered
(beaconing)** AND **paired (in the persistent store)** — until
both hold, no remote sessions appear.

## What the dashboard shows you

In the Config pane's Federation subsection, every visible peer
gets a row with one action button:

| Status | Meaning | Button |
|---|---|---|
| `discovered` | beaconing, not paired, no activity | **Request Pair** |
| `request-sent` | you asked them, awaiting response | (none) |
| `request-pending` | they asked you, awaiting decision | **Accept** / **Decline** |
| `paired` (online) | beaconing + in your paired set | **Unpair** |
| `paired` (offline) | in your paired set, not beaconing | **Unpair** |

The badge in the section header counts actionable rows
(paired + request-pending + request-sent), so an incoming
request is visible without expanding the section.

## Aggregated session UX

Once paired, each peer's `/api/sessions` is fetched in parallel on
every dashboard refresh (1.5s per-peer timeout, 2s total budget).
Remote rows arrive with:

- `name` prefixed by the peer's hostname (`hostA:work`);
- a hostname badge in the summary row (accent blue for remote;
  the local rows show a subtle grey badge with your own hostname
  when at least one remote is also visible, for symmetry);
- `peer_url` and `device_id` tags so per-pane interactions
  (start/stop ttyd, kill, etc.) route through the peer's HTTP
  surface, and the iframe loads ttyd directly from the peer's
  port.

## Trust model

Discovery is unauthenticated by design — anyone on the same LAN
segment can broadcast a beacon. **The pairing handshake is the
trust gate**. A hostile peer can:

- broadcast a beacon with whatever hostname it likes, so its
  display name in your "discovered" list is its own choice;
- send unsolicited `pair-request` messages to your dashboard
  (which queue as pending until you accept or decline);

A hostile peer **cannot**:

- write itself into your paired set without an operator click on
  your side;
- read your sessions, because the merge runs from your side and
  only fetches paired peers' `/api/sessions`;
- silently re-pair after you've unpaired (no replay attack: each
  `pair-accept-callback` requires a fresh outgoing record on
  the receiver, which only `Request Pair` creates).

## Network requirements

UDP port 8095 must be reachable in both directions on the LAN
for discovery to work. The pair-request/accept HTTP calls go to
each peer's dashboard port (default 8096) — same network
requirement as the dashboard itself.

The browser's iframe loads from each peer's ttyd port range
(default 7700-7799). If a peer binds those to `127.0.0.1` only,
the federated panes won't expand from your browser; document or
set `--bind 0.0.0.0` (the default) on each peer.

## Same scheme across peers

A dashboard running over HTTPS cannot embed an iframe from a peer
running plain HTTP — browsers block mixed content. Run all peers
on the same scheme.

If your dashboard is HTTPS, every peer's ttyd needs HTTPS too;
the scheme is forwarded through `--cert`/`--key` automatically
(see `docs/dashboard.md`).

## Disabling federation

There are two scopes for "off":

- **Permanent (uninstall the extension).**
  `make disable-federation` flips `enabled=false` in
  `~/.tmux-browse/extensions.json`; restart the dashboard and
  federation no longer loads. `make uninstall-federation` removes
  the submodule code too. Either preserves
  `~/.tmux-browse/paired-peers.json` so a later re-enable restores
  the same pairings; `make uninstall-federation-with-state` also
  deletes the paired set.

- **Per-run override.** `tmux_browse.py serve --no-federation`
  skips loading the federation extension for one run, even if it's
  enabled in `extensions.json`. The host won't beacon (invisible
  to peers) and won't accept incoming beacons (won't see them).
  Existing paired records persist; the next normal start restores
  them. No-op if the extension isn't installed at all.

To unpair without disabling federation entirely, click **Unpair**
in the Federation Config card. We don't notify the peer when you
unpair — their pairing state is theirs. Their next beacon will
land in your `discovered` list and you can re-pair if you want.

## Limitations

- **Two tmux-browse processes on one host.** Only one binds the
  UDP listener port. The second still broadcasts (it's visible
  to peers) but can't see incoming beacons. Logged at WARN at
  startup.
- **No proxy mode.** Browsers connect directly to peer ttyd ports.
  If a peer's port range isn't reachable from your browser,
  federation looks half-broken (sessions visible in the list,
  expanding fails to load).
- **No auth-token forwarding between peers.** If you run with
  `--auth $TOKEN`, each peer enforces its own token on
  `/api/sessions` — peers with mismatched tokens get an empty
  session list from each other. Pair across hosts with uniform
  auth (or no auth on either end).
- **Pairing is per-process.** The `~/.tmux-browse/paired-peers.json`
  file is per-host but a kill-9 mid-write (very narrow race) could
  corrupt it; we use atomic .tmp + replace to keep that window
  small.
- **Pending requests are RAM-only.** A server restart drops any
  pending incoming request. The other side can re-send.

## Verifying it works

```bash
# On hostA
tmux-browse serve &

# On hostB (same LAN, ≥10 seconds later)
tmux-browse serve &
curl -s http://localhost:8096/api/peers | python3 -m json.tool
```

You should see `hostA` in the peer list with status `discovered`.
Open hostB's dashboard, expand Config → Federation, click
**Request Pair** on hostA. On hostA, accept. Both should now show
the other with status `paired (online)`, and each side's
dashboard shows the other's tmux sessions prefixed with the
peer's hostname.

## Firewall note

Most home networks don't filter LAN UDP, but `iptables`, `ufw`,
or corporate firewalls might.

```bash
# Allow on Linux + ufw
sudo ufw allow proto udp from any to any port 8095

# Quick check that beacons are flowing
sudo tcpdump -ni any 'udp port 8095' -c 5
```
