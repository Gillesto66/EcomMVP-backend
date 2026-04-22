# Auteur : Gilles - Projet : AGC Space - Module : URLs Principal
import os
from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static


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

    try:
        t0 = time.monotonic()
        connection.ensure_connection()
        db_latency_ms = round((time.monotonic() - t0) * 1000)
    except Exception as e:
        db_ok = False
        import logging
        logging.getLogger('security').error("Health check — DB KO : %s", str(e))

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

# Fichiers media en développement uniquement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ── Proxy Next.js — dev local uniquement ─────────────────────────────────────
# Sur Render (et tout environnement cloud), le frontend est servi par Vercel.
# Le proxy n'est activé que si NEXTJS_INTERNAL_URL est défini ET qu'on est en DEBUG.
_NEXTJS_URL = os.getenv('NEXTJS_INTERNAL_URL', '')
if settings.DEBUG and _NEXTJS_URL:
    from agc_core.proxy import nextjs_proxy
    urlpatterns += [
        re_path(r'^.*$', nextjs_proxy, name='nextjs-proxy'),
    ]
