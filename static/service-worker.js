// Minimal service worker — caches the PWA shell only (manifest +
// icons + favicon). The dashboard HTML and inline JS come from "/"
// and are NOT cached, so a server restart is reflected on next
// navigation. /api/* is also never cached: stale session data
// would defeat the dashboard's purpose.

const CACHE = "tmux-browse-v1";
const SHELL = [
    "/manifest.webmanifest",
    "/pwa-192.png",
    "/pwa-512.png",
    "/favicon.svg",
];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
});

self.addEventListener("activate", (e) => {
    e.waitUntil(caches.keys().then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)),
    )));
});

self.addEventListener("fetch", (e) => {
    const u = new URL(e.request.url);
    // Never cache the dashboard HTML or any API call. Return early
    // so the browser does its normal network fetch.
    if (u.pathname === "/" || u.pathname.startsWith("/api/")) return;
    e.respondWith(
        caches.match(e.request).then((r) => r || fetch(e.request)),
    );
});
