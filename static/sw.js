// static/sw.js
// ============================================================
// Service worker de "Ma Boutik" — condition technique pour que
// Chrome/Edge/Android proposent l'installation de l'application (icône
// sur l'écran d'accueil / bouton "Installer"). Voir login_page.html,
// dashboard_boutique.html, dashboard_vendeur.html pour l'enregistrement.
//
// Stratégie volontairement prudente : les données ici sont du stock, des
// ventes, des montants — jamais de valeur périmée affichée depuis un
// cache. Seuls le manifest et les icônes (immuables) sont mis en cache ;
// tout le reste passe TOUJOURS par le réseau d'abord, le cache ne sert
// qu'en dernier recours si la boutique est hors-ligne.
// ============================================================

const CACHE_NAME = 'ma-boutik-v1';
const ASSETS_STATIQUES = [
    '/app-manifest.json',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(ASSETS_STATIQUES))
            .catch(() => {})
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cles) => Promise.all(
            cles.filter((cle) => cle !== CACHE_NAME).map((cle) => caches.delete(cle))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const { request } = event;
    if (request.method !== 'GET') return;

    const estAssetStatique = ASSETS_STATIQUES.some((url) => request.url.endsWith(url));
    if (estAssetStatique) {
        // Rapide, change rarement : cache d'abord, réseau en secours.
        event.respondWith(
            caches.match(request).then((reponse) => reponse || fetch(request))
        );
        return;
    }

    // Tout le reste (pages, API) : réseau d'abord — la version qui vient
    // d'être déployée est donc visible dès le prochain chargement de page.
    // Cache uniquement utilisé si hors-ligne.
    event.respondWith(
        fetch(request)
            .then((reponse) => {
                if (reponse && reponse.ok) {
                    const copie = reponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copie)).catch(() => {});
                }
                return reponse;
            })
            .catch(() => caches.match(request))
    );
});
