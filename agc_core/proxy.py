# Auteur : Gilles - Projet : AGC Space - Module : Proxy Next.js
"""
Reverse proxy Django → Next.js avec streaming.

Les assets Next.js peuvent dépasser 6 MB (main-app.js).
Sans streaming, httpx charge tout en mémoire → Broken pipe sur les gros fichiers.
Avec streaming, les chunks sont transmis au fur et à mesure → pas de timeout.
"""
import logging
import os
import httpx
from django.http import HttpResponse, StreamingHttpResponse

logger = logging.getLogger('security')

NEXTJS_URL = os.getenv('NEXTJS_INTERNAL_URL', 'http://127.0.0.1:3000')

# Headers hop-by-hop — ne pas transmettre
_HOP_BY_HOP = frozenset([
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade',
    'content-length',  # httpx recalcule
])

# Taille des chunks de streaming (32 KB)
_CHUNK_SIZE = 32 * 1024

# Extensions d'assets statiques — toujours streamés
_STATIC_EXTENSIONS = frozenset([
    '.js', '.css', '.woff', '.woff2', '.ttf', '.eot',
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
    '.map', '.json',
])


def _is_static_asset(path: str) -> bool:
    """Retourne True si le path est un asset statique Next.js."""
    if path.startswith('/_next/'):
        return True
    ext = os.path.splitext(path.split('?')[0])[1].lower()
    return ext in _STATIC_EXTENSIONS


def _forward_headers(request) -> dict:
    """Extrait les headers HTTP de la requête Django pour httpx."""
    headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_'):
            name = key[5:].replace('_', '-').lower()
            if name not in _HOP_BY_HOP:
                headers[name] = value
        elif key == 'CONTENT_TYPE' and value:
            headers['content-type'] = value

    headers['x-forwarded-for'] = request.META.get('REMOTE_ADDR', '')
    headers['x-forwarded-proto'] = 'https' if request.is_secure() else 'http'
    headers['x-forwarded-host'] = request.get_host()
    # Bypass la page d'avertissement Ngrok
    headers['ngrok-skip-browser-warning'] = '1'
    return headers


def nextjs_proxy(request):
    """
    Vue catch-all : transmet la requête au serveur Next.js.

    - Assets statiques (/_next/*) : streaming par chunks de 32 KB
      → évite les Broken pipe sur les gros fichiers JS (6 MB+)
    - Pages HTML : réponse complète (petite taille, pas de problème)
    """
    path = request.get_full_path()
    target_url = f"{NEXTJS_URL}{path}"
    headers = _forward_headers(request)
    body = request.body if request.method not in ('GET', 'HEAD', 'OPTIONS') else None

    is_asset = _is_static_asset(path)

    try:
        if is_asset:
            # ── Streaming pour les assets statiques ───────────────────────────
            return _stream_response(request.method, target_url, headers, body)
        else:
            # ── Réponse complète pour les pages HTML ──────────────────────────
            return _full_response(request.method, target_url, headers, body)

    except httpx.ConnectError:
        logger.error("Proxy Next.js : connexion refusée — Next.js est-il démarré ?")
        return HttpResponse(
            content=_nextjs_down_page(),
            status=503,
            content_type='text/html; charset=utf-8',
        )
    except httpx.TimeoutException:
        logger.error("Proxy Next.js : timeout sur %s %s", request.method, path)
        return HttpResponse('<h1>503 — Timeout</h1>', status=503, content_type='text/html')
    except Exception as e:
        logger.error("Proxy Next.js : erreur inattendue : %s", str(e))
        return HttpResponse(f'<h1>502</h1><p>{e}</p>', status=502, content_type='text/html')


def _full_response(method: str, url: str, headers: dict, body) -> HttpResponse:
    """Réponse complète — pour les pages HTML (petite taille)."""
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        resp = client.request(method=method, url=url, headers=headers, content=body)

    response_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    django_resp = HttpResponse(
        content=resp.content,
        status=resp.status_code,
        content_type=resp.headers.get('content-type', 'text/html'),
    )
    for k, v in response_headers.items():
        if k.lower() != 'content-type':
            django_resp[k] = v
    django_resp['ngrok-skip-browser-warning'] = '1'
    return django_resp


def _stream_response(method: str, url: str, headers: dict, body) -> StreamingHttpResponse:
    """
    Streaming par chunks — pour les assets statiques volumineux.
    Évite de charger 6 MB en mémoire et les Broken pipe.
    """
    # On ouvre le client en dehors du with pour que le streaming reste ouvert
    client = httpx.Client(timeout=60.0, follow_redirects=False)
    req = client.build_request(method=method, url=url, headers=headers, content=body)
    resp = client.send(req, stream=True)

    content_type = resp.headers.get('content-type', 'application/octet-stream')

    def generate():
        try:
            for chunk in resp.iter_bytes(chunk_size=_CHUNK_SIZE):
                yield chunk
        finally:
            resp.close()
            client.close()

    django_resp = StreamingHttpResponse(
        streaming_content=generate(),
        status=resp.status_code,
        content_type=content_type,
    )

    # Transmettre les headers utiles (cache, etag, etc.)
    for k, v in resp.headers.items():
        if k.lower() not in _HOP_BY_HOP and k.lower() != 'content-type':
            django_resp[k] = v

    django_resp['ngrok-skip-browser-warning'] = '1'
    return django_resp


def _nextjs_down_page() -> str:
    return """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>AGC Space — Frontend indisponible</title>
<style>
  body{font-family:system-ui,sans-serif;display:flex;align-items:center;
       justify-content:center;min-height:100vh;margin:0;background:#f8fafc}
  .card{background:white;border-radius:1rem;padding:2.5rem;max-width:480px;
        text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.08)}
  code{background:#f1f5f9;padding:.2rem .5rem;border-radius:.25rem;font-size:.875rem}
</style>
</head>
<body>
  <div class="card">
    <h1 style="color:#0f172a">⚠️ Frontend indisponible</h1>
    <p style="color:#64748b">Next.js n'est pas démarré.<br>Lancez-le avec :</p>
    <p><code>cd frontend && npm run dev</code></p>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:1.5rem 0">
    <p style="font-size:.8rem;color:#94a3b8">L'API reste accessible sur <code>/api/v1/</code></p>
  </div>
</body>
</html>"""
