# Auteur : Gilles - Projet : AGC Space - Module : Middleware
"""
Middlewares personnalisés AGC Space.

RequestLoggingMiddleware :
  - Log structuré de chaque requête HTTP (méthode, path, statut, durée, IP)
  - Exclut les endpoints de health check et les assets statiques (bruit inutile)
  - Alerte si une requête dépasse 1 seconde (performance warning)
"""
import logging
import os
import time

logger = logging.getLogger('security')
perf_logger = logging.getLogger('products')  # Réutilise le logger produits pour les perfs

# Paths à exclure des logs (trop verbeux, pas d'intérêt métier)
_EXCLUDED_PATHS = frozenset([
    '/health/',
    '/static/',
    '/media/',
    '/favicon.ico',
    '/_next/',  # Assets Next.js — trop verbeux
])

# Seuil d'alerte performance (secondes)
_SLOW_REQUEST_THRESHOLD = float(os.getenv('SLOW_REQUEST_THRESHOLD', '10.0'))
# En dev Next.js compile à la demande (JIT) → premières requêtes lentes (5-15s) — normal


class RequestLoggingMiddleware:
    """
    Middleware de logging structuré des requêtes HTTP.

    Log format :
      [INFO] GET /api/v1/render/42/ → 200 (45ms) — 1.2.3.4
      [WARNING] POST /api/v1/orders/create/ → 500 (1250ms) — SLOW REQUEST
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Exclure les paths non pertinents
        path = request.path
        if any(path.startswith(excluded) for excluded in _EXCLUDED_PATHS):
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000)

        client_ip = self._get_client_ip(request)
        method = request.method
        status_code = response.status_code

        # Log niveau selon le statut HTTP
        if status_code >= 500:
            log_fn = logger.error
        elif status_code >= 400:
            log_fn = logger.warning
        else:
            log_fn = logger.info

        log_fn(
            "%s %s -> %d (%dms) — %s",
            method, path, status_code, duration_ms, client_ip,
        )

        # Alerte performance si la requête est trop lente
        if duration_ms > _SLOW_REQUEST_THRESHOLD * 1000:
            perf_logger.warning(
                "SLOW REQUEST : %s %s -> %dms (seuil: %dms) — IP: %s",
                method, path, duration_ms, int(_SLOW_REQUEST_THRESHOLD * 1000), client_ip,
            )

        return response

    @staticmethod
    def _get_client_ip(request) -> str:
        """Extrait l'IP réelle du client (derrière Nginx/proxy)."""
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
