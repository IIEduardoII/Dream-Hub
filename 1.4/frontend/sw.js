// Dream Hub v1.4.0 - Online-First PWA Service Worker (WebAPK Ready, Zero Stale Cache)
const SW_VERSION = 'dreamhub-pwa-v1.4.0';

const OFFLINE_FALLBACK_HTML = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#000000">
  <title>Dream Hub • Sem Conexão</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #000000;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      text-align: center;
    }
    .card {
      max-width: 360px;
      width: 100%;
      background: #0d1117;
      border: 1px solid #21262d;
      border-radius: 16px;
      padding: 28px 22px;
    }
    .dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #f87171;
      margin: 0 auto 16px;
      box-shadow: 0 0 14px rgba(248, 113, 113, 0.55);
    }
    h1 { font-size: 1.15rem; margin-bottom: 8px; }
    p { font-size: 0.875rem; color: #94a3b8; line-height: 1.5; margin-bottom: 20px; }
    button {
      width: 100%;
      min-height: 48px;
      border-radius: 10px;
      border: none;
      background: #38bdf8;
      color: #000000;
      font-weight: 700;
      font-size: 0.95rem;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="dot"></div>
    <h1>Servidor Indisponível</h1>
    <p>Verifique se o <strong>Tailscale</strong> está ativo no seu celular e se o servidor Termux está online.</p>
    <button onclick="window.location.reload()">Tentar Novamente</button>
  </div>
</body>
</html>`;

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Pass-through estritamente online (sem cache obsoleto nem fila offline)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(OFFLINE_FALLBACK_HTML, {
          status: 503,
          headers: { 'Content-Type': 'text/html; charset=utf-8' }
        })
      )
    );
    return;
  }

  event.respondWith(fetch(event.request));
});
