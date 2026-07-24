/**
 * 1CRYPTEN SNIPER PWA SERVICE WORKER
 * Version: V110.183.0 (Dynamic Bypass & Safe Response Fix)
 * Strategies: 
 * - Network-First: Main Logic & HTML (Always fresh if online)
 * - Cache-First: Static Assets & Vendor (Instant load)
 * - Stale-While-Revalidate: Manifest & CDNs
 */

const CACHE_NAME = '1crypten-sniper-v133.0'; // [V133] PWA fix: boot shield restored, SW destruction removed
const OFFLINE_URL = '/offline.html';

// Assets que devem estar disponíveis offline (caminhos absolutos baseados na raiz)
const STATIC_ASSETS = [
    '/cockpit.html',
    '/css/cockpit.css',
    '/app.js',
    '/components/TriumphModal.js',
    '/components/SettingsPage.js',
    '/components/AdminUsersPage.js',
    '/components/TakeoffModal.js',
    '/components/DeepAnalysisModal.js',
    '/offline.html',
    '/manifest.json',
    '/logo10D.png',
    '/logo10DTrasp.png',
    '/favicon.ico'
];

// Instalação: Cacheia arquivos críticos de forma resiliente
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Pre-caching critical assets');
            // Tenta cachear um por um para evitar que a falha de um único arquivo quebre toda a instalação
            const cachePromises = STATIC_ASSETS.map((asset) => {
                return cache.add(asset).catch((err) => {
                    console.warn(`[SW] Falha ao cachear o asset: ${asset}`, err);
                });
            });
            return Promise.all(cachePromises);
        })
    );
    self.skipWaiting();
});

// Ativação: Limpa caches antigos
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
            );
        })
    );
    console.log('[SW] V125.600 Activated (Menu padronizado) ✅');
    return self.clients.claim();
});

// Interceptor de Fetch
self.addEventListener('fetch', (event) => {
    // Apenas requisições GET
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // 1. BYPASS para APIs, WebSockets, OKX, Observatory e Login (Dynamic Paths)
    if (url.pathname.startsWith('/api/') ||
        url.pathname.startsWith('/observatory/') ||
        url.pathname === '/observatory' ||
        url.pathname === '/login' ||
        url.pathname === '/login.html' ||
        url.pathname === '/auth' ||
        url.pathname === '/auth.html' ||
        url.hostname.includes('firebaseio.com') ||
        url.hostname.includes('okx.com') ||
        url.hostname.includes('railway.app')) {
        return; // Network Only (Bypass total do Service Worker!)
    }

    // 2. Network-First para páginas principais e manifest
    // Isso garante que se houver internet, o usuário pegue a versão mais nova.
    if (url.pathname === '/' || url.pathname === '/cockpit.html' || url.pathname === '/manifest.json' || url.pathname === '/neural-chat') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const clonedResponse = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clonedResponse);
                    });
                    return response;
                })
                .catch(() => {
                    return caches.match(event.request).then((cached) => {
                        return cached || caches.match(OFFLINE_URL);
                    });
                })
        );
        return;
    }

    // 3. Cache-First para Vendor e Imagens Locais
    if (url.pathname.startsWith('/vendor/') || url.pathname.endsWith('.png') || url.pathname.endsWith('.ico')) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    const clonedResponse = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clonedResponse);
                    });
                    return response;
                });
            })
        );
        return;
    }

    // 4. Stale-While-Revalidate para CDNs (Tailwind, Google Fonts, etc)
    if (url.hostname.includes('gstatic.com') || 
        url.hostname.includes('googleapis.com') || 
        url.hostname.includes('jsdelivr.net') ||
        url.hostname.includes('tailwindcss.com')) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                const networkFetch = fetch(event.request).then((response) => {
                    const clonedResponse = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clonedResponse);
                    });
                    return response;
                });
                return cached || networkFetch;
            })
        );
        return;
    }

    // Default: Stale-While-Revalidate
    event.respondWith(
        caches.match(event.request).then((cached) => {
            const networkFetch = fetch(event.request).then((response) => {
                if (!response || response.status !== 200 || response.type !== 'basic') return response;
                const clonedResponse = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(event.request, clonedResponse);
                });
                return response;
            }).catch(() => cached || new Response('Offline', { status: 503, statusText: 'Service Unavailable' }));
            return cached || networkFetch;
        })
    );
});

// Listener para mensagens (Update Protocol)
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// [HERMES] Push Notification Listener
self.addEventListener('push', (event) => {
    if (!event.data) return;
    
    try {
        const data = event.data.json();
        const options = {
            body: data.message || data.body || 'Nova notificacao do Hermes',
            icon: '/logo10DTrasp.png?v=4',
            badge: '/logo10DTrasp.png?v=4',
            vibrate: [200, 100, 200],
            data: {
                url: data.url || '/',
                timestamp: Date.now()
            },
            actions: [
                { action: 'open', title: 'Abrir Cockpit' },
                { action: 'dismiss', title: 'Ignorar' }
            ]
        };
        
        event.waitUntil(
            self.registration.showNotification(
                data.title || 'HERMES - 10D Fleet',
                options
            )
        );
    } catch (e) {
        // Fallback for plain text push
        event.waitUntil(
            self.registration.showNotification('HERMES - 10D Fleet', {
                body: event.data.text(),
                icon: '/logo10DTrasp.png?v=4'
            })
        );
    }
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    if (event.action === 'dismiss') return;
    
    const urlToOpen = event.notification.data?.url || '/';
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            // Check if there's already a window open
            for (const client of windowClients) {
                if (client.url.includes(urlToOpen) && 'focus' in client) {
                    return client.focus();
                }
            }
            // Open new window
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});
