// Service Worker for Invoice AI
// Provides offline capabilities and caching for better performance

const CACHE_NAME = 'invoice-ai-v1';
const CACHE_ASSETS = [
    '/',
    '/static/optimized/css/style.4c827829.min.css',
    '/static/optimized/js/bundle.9248c07b.min.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css',
    'https://cdn.jsdelivr.net/npm/chart.js'
];

// Install Service Worker
self.addEventListener('install', event => {
    console.log('Service Worker: Installing');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Service Worker: Caching assets');
                return cache.addAll(CACHE_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate Service Worker
self.addEventListener('activate', event => {
    console.log('Service Worker: Activating');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cache => {
                    if (cache !== CACHE_NAME) {
                        console.log('Service Worker: Clearing old cache');
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
});

// Fetch Event
self.addEventListener('fetch', event => {
    console.log('Service Worker: Fetching');
    
    // Cache-first strategy for static assets
    if (event.request.url.includes('/static/') || 
        event.request.url.includes('bootstrap') || 
        event.request.url.includes('chart.js')) {
        
        event.respondWith(
            caches.match(event.request)
                .then(response => {
                    if (response) {
                        return response;
                    }
                    return fetch(event.request)
                        .then(fetchResponse => {
                            if (!fetchResponse || fetchResponse.status !== 200) {
                                return fetchResponse;
                            }
                            
                            const responseClone = fetchResponse.clone();
                            caches.open(CACHE_NAME)
                                .then(cache => {
                                    cache.put(event.request, responseClone);
                                });
                            
                            return fetchResponse;
                        });
                })
        );
    }
    // Network-first strategy for API calls
    else if (event.request.url.includes('/api/') || 
             event.request.url.includes('/upload') ||
             event.request.url.includes('/extraction')) {
        
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    if (!response || response.status !== 200) {
                        return response;
                    }
                    
                    // Cache successful API responses for 5 minutes
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME)
                        .then(cache => {
                            cache.put(event.request, responseClone);
                        });
                    
                    return response;
                })
                .catch(() => {
                    // Fallback to cache if network fails
                    return caches.match(event.request);
                })
        );
    }
    // Default: network-first with cache fallback
    else {
        event.respondWith(
            fetch(event.request)
                .catch(() => {
                    return caches.match(event.request);
                })
        );
    }
});

// Background sync for failed uploads
self.addEventListener('sync', event => {
    if (event.tag === 'background-sync') {
        console.log('Service Worker: Background sync triggered');
        event.waitUntil(doBackgroundSync());
    }
});

async function doBackgroundSync() {
    // Implement background sync logic for failed uploads
    try {
        const cache = await caches.open(CACHE_NAME);
        const requests = await cache.keys();
        
        // Find failed upload requests
        const failedUploads = requests.filter(req => 
            req.url.includes('/upload') && 
            req.method === 'POST'
        );
        
        // Retry failed uploads
        for (const request of failedUploads) {
            try {
                const response = await fetch(request);
                if (response.ok) {
                    await cache.delete(request);
                }
            } catch (error) {
                console.error('Background sync failed:', error);
            }
        }
    } catch (error) {
        console.error('Background sync error:', error);
    }
}

// Message handling for cache updates
self.addEventListener('message', event => {
    if (event.data.action === 'skipWaiting') {
        self.skipWaiting();
    }
    
    if (event.data.action === 'clearCache') {
        caches.delete(CACHE_NAME);
    }
    
    if (event.data.action === 'updateCache') {
        caches.open(CACHE_NAME)
            .then(cache => {
                cache.addAll(CACHE_ASSETS);
            });
    }
});

// Notification click handler
self.addEventListener('notificationclick', event => {
    console.log('Notification click received.');
    
    event.notification.close();
    
    event.waitUntil(
        clients.openWindow('/')
    );
});

// Push event handler for future notifications
self.addEventListener('push', event => {
    console.log('Push message received.');
    
    const title = 'Invoice AI';
    const options = {
        body: event.data ? event.data.text() : 'Processing complete',
        icon: '/static/img/favicon.png',
        badge: '/static/img/favicon.png'
    };
    
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});