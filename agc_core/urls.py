# Auteur : Gilles - Projet : AGC Space - Module : URLs Principal
import os
from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static
from agc_core.proxy import nextjs_proxy


def health_check(request):
    """
    Endpoint de health check pour Nginx et les outils de monitoring.
    Vérifie DB + Redis + retourne des métriques basiques.
    Retourne 200 si tout est OK, 503 si dégradé.
    """
    import time
    from django.db import connection
    from django.core.cache import cache

    db_ok, cache_ok = True, True
    db_latency_ms, cache_latency_ms = None, None

    # ── Vérification DB ───────────────────────────────────────────────────────
    try:
        t0 = time.monotonic()
        connection.ensure_connection()
        db_latency_ms = round((time.monotonic() - t0) * 1000)
    except Exception as e:
        db_ok = False
        import logging
        logging.getLogger('security').error("Health check — DB KO : %s", str(e))

    # ── Vérification Redis ────────────────────────────────────────────────────
    try:
        t0 = time.monotonic()
        cache.set('health_check', '1', 5)
        cache_ok = cache.get('health_check') == '1'
        cache_latency_ms = round((time.monotonic() - t0) * 1000)
    except Exception as e:
        cache_ok = False
        import logging
        logging.getLogger('security').error("Health check — Redis KO : %s", str(e))

    http_status = 200 if (db_ok and cache_ok) else 503
    return JsonResponse({
        'status': 'ok' if http_status == 200 else 'degraded',
        'db': {'status': 'ok' if db_ok else 'error', 'latency_ms': db_latency_ms},
        'cache': {'status': 'ok' if cache_ok else 'error', 'latency_ms': cache_latency_ms},
        'version': os.getenv('APP_VERSION', 'unknown'),
    }, status=http_status)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health-check'),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/', include('products.urls')),
    path('api/v1/affiliations/', include('affiliations.urls')),
    path('api/v1/orders/', include('orders.urls')),
]

# Servir les fichiers media en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ── Catch-all : tout le reste → Next.js ──────────────────────────────────────
# DOIT être en dernier — après toutes les routes API et media
urlpatterns += [
    re_path(r'^.*$', nextjs_proxy, name='nextjs-proxy'),
]
