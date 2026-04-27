# LAN federation

When two or more tmux-browse instances run on the same broadcast
domain (a LAN segment), they auto-discover each other and merge
their session lists. The dashboard you have open shows panes from
every visible peer, with each remote session's name prefixed by
the originating peer's hostname (`hostA:work`).

This is intended for the "I have tmux-browse on my workstation
and on a Pi by the bench, both on my home network, I want one
dashboard" case — not for cross-internet aggregation, not for
shared networks.

## How discovery works

Each instance broadcasts a tiny JSON beacon to UDP
`255.255.255.255:8095` every five seconds:

```json
{
  "device_id": "1c7d…",
  "hostname": "hostA",
  "dashboard_port": 8096,
  "scheme": "http",
  "version": "0.7.3.0",
  "beacon_seq": 42
}
```

The same instance also listens on UDP 8095. Each beacon it
receives lands in the in-memory peer registry with the source IP
attached. Peers expire 15 seconds after their last beacon (3×
the cadence, so a single dropped packet doesn't drop the peer).

There's no mDNS, no zeroconf, no central registry. Just UDP
broadcast, which works on any LAN by default.

## How aggregation works

When the dashboard renders `/api/sessions`, it fetches each live
peer's `/api/sessions` in parallel (with a 1.5s per-peer timeout
and a 2s total budget). Each remote session row is:

- prefixed with `<hostname>:` so the names don't collide;
- tagged with the peer's `device_id` and `peer_url` so the
  dashboard knows it's remote;
- merged into the local list as if it were just another row.

Per-pane interactions (start/stop ttyd, kill, etc.) route
through the peer's HTTP surface for remote rows. The browser
loads the iframe directly from the peer's ttyd port — no proxy
through the local server.

## Trust model

> **Important:** any host on the same LAN can broadcast a beacon
> claiming to be a tmux-browse peer. The discovery layer doesn't
> authenticate the source. Federation is appropriate for trusted
> single-user / single-tenant LANs only.

Specifically:

- A malicious peer on the LAN could advertise itself, and your
  dashboard would show its sessions in your list. Clicking one
  loads its ttyd in your browser — not exfil-shaped, but trust
  is still the right gate.
- Auth tokens are not validated across peers. If the local
  dashboard runs with `--auth $TOKEN` and a peer doesn't, the
  peer's `/api/sessions` will refuse the unauthenticated fetch
  and contribute nothing — which is the right outcome (uniform
  auth across the cluster, or no auth, but not mismatched).

To disable on a host: `tmux-browse serve --no-federation`. The
host stops broadcasting, stops listening, and no peer rows
appear in its dashboard. Re-enable by removing the flag and
restarting.

## Limitations

- **Same scheme across peers.** A dashboard running over HTTPS
  cannot embed an iframe from a peer running plain HTTP — the
  browser blocks mixed content. Run all peers HTTP, or all
  HTTPS.
- **One dashboard per host beacons.** If two tmux-browse
  processes run on the same host, only one binds the listener
  port. The other still broadcasts (it's visible to peers) but
  can't see incoming beacons. Logged at WARN at startup.
- **No proxy mode.** Browsers connect directly to peer ttyd
  ports. If a peer's port range (default 7700-7799) isn't
  reachable from your browser, federation looks half-broken
  (sessions visible in the list, expanding fails to load).
  Same fix as for any remote ttyd: `--bind 0.0.0.0` (default)
  or open the firewall.
- **No auth handshake between peers.** Peers expect the same
  auth token (or no auth) on both ends. Mismatched auth = the
  peer's sessions silently don't appear. Future work could
  formalise per-pair handshake; not implemented.

## Disabling

```bash
tmux-browse serve --no-federation
```

Run on every peer where you don't want discovery. The flag
takes effect for that process only — restart to apply.

## Verifying it works

```bash
# On hostA
tmux-browse serve &

# On hostB (same LAN, ≥10 seconds later)
tmux-browse serve &
curl -s http://localhost:8096/api/peers | python3 -m json.tool
```

You should see `hostA` in the peer list. Open the dashboard:
hostA's sessions appear with the `hostA:` prefix. Killing one of
hostA's sessions from hostB's dashboard works (the request
routes through to hostA's `/api/session/kill`).

## Firewall note

UDP port 8095 must be reachable in both directions on the LAN.
Most home networks don't filter LAN UDP, but `iptables`,
`ufw`, or corporate firewalls might. Quick test:

```bash
# On hostA
sudo tcpdump -ni any 'udp port 8095' -c 5

# On hostB (separate shell)
tmux-browse serve --no-federation false &  # if already running, skip
```

You should see packets from both hosts flowing through.

If beacons aren't arriving:

```bash
# Allow on Linux + ufw
sudo ufw allow proto udp from any to any port 8095

# Or temporarily verify with a test packet
echo '{"device_id":"manual-test","hostname":"manual","dashboard_port":1,"scheme":"http","version":"t"}' \
    | nc -uw 1 -b 255.255.255.255 8095
```
