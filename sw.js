/* Alertas HSEC por Comuna — trabajador de servicio.
   Permite abrir la aplicación sin señal: guarda la página, el mapa y las
   alertas de la última visita. Las alertas se piden siempre a la red
   primero, para no mostrar información vieja cuando sí hay conexión. */
const VERSION = "hsec-v1";
const BASE = new URL("./", self.location).pathname;

// Lo imprescindible para que la aplicación abra sin conexión.
const ESENCIAL = ["./", "./index.html", "./mapdata.json", "./alerts.json", "./manifest.webmanifest"];
// Útil pero no crítico: si alguno falla, la instalación sigue adelante.
const EXTRA = [
  "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png",
  "./help/mapa.jpg", "./help/movil.jpg", "./help/planilla.jpg",
  "./help/contacto.jpg", "./help/oficinas.jpg",
  "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js",
  "https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js",
  "https://cdn.jsdelivr.net/npm/jspdf-autotable@3.8.2/dist/jspdf.plugin.autotable.min.js"
];

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    await c.addAll(ESENCIAL);
    await Promise.allSettled(EXTRA.map(u => c.add(new Request(u, { mode: "cors" }))));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const viejas = (await caches.keys()).filter(k => k !== VERSION);
    await Promise.all(viejas.map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

// Permite que la página pida actualizar de inmediato.
self.addEventListener("message", e => { if (e.data === "actualizar") self.skipWaiting(); });

const red = async (req, c) => {
  const r = await fetch(req);
  if (r && r.ok && req.method === "GET") c.put(req, r.clone());
  return r;
};

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const propio = url.origin === self.location.origin;
  const esAlertas = propio && url.pathname.endsWith("alerts.json");
  const esPagina = req.mode === "navigate";

  // Alertas y navegación: primero la red, para no quedarse con datos viejos.
  if (esAlertas || esPagina) {
    e.respondWith((async () => {
      const c = await caches.open(VERSION);
      try {
        return await red(req, c);
      } catch (_) {
        const guardado = await c.match(req, { ignoreSearch: true })
          || (esPagina ? await c.match("./index.html") : null);
        if (guardado) return guardado;
        throw _;
      }
    })());
    return;
  }

  // El resto: primero lo guardado, y se refresca por detrás.
  if (propio || EXTRA.some(u => req.url.startsWith(u.split("?")[0]))) {
    e.respondWith((async () => {
      const c = await caches.open(VERSION);
      const guardado = await c.match(req, { ignoreSearch: true });
      if (guardado) { e.waitUntil(red(req, c).catch(() => {})); return guardado; }
      return red(req, c);
    })());
  }
});
