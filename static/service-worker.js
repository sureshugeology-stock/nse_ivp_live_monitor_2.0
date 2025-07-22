self.addEventListener("install", e => {
  e.waitUntil(
    caches.open("nse-ivp-cache").then(cache => {
      return cache.addAll([
        "/nse_ivp_live_monitor_2.0/",
        "/nse_ivp_live_monitor_2.0/static/nifty_ivp_live_plot.png",
        "/nse_ivp_live_monitor_2.0/static/banknifty_ivp_live_plot.png"
      ]);
    })
  );
});

self.addEventListener("fetch", e => {
  e.respondWith(
    caches.match(e.request).then(response => {
      return response || fetch(e.request);
    })
  );
});