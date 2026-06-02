const CACHE = "vc-v3";
const ASSETS = [
    "/",
    "/static/css/style.css",
    "/static/js/app.js",
    "/static/js/notes.js",
    "/static/manifest.json",
];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
});

self.addEventListener("fetch", (e) => {
    if (e.request.url.includes("/api/")) {
        // API 请求走网络，不缓存
        return;
    }
    e.respondWith(
        caches.match(e.request).then((r) => r || fetch(e.request))
    );
});
