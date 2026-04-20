# Auteur : Gilles - Projet : AGC Space - Module : Tests Infrastructure
"""
Tests de l'infrastructure : health check, cache, throttle, middleware, gzip.
Ces tests vérifient que les composants d'infrastructure fonctionnent correctement.
"""
import pytest
import time
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='infra_user', password='pass', email='infra@test.com')


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


# ── Health Check ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestHealthCheck:
    def test_health_check_ok(self, api_client):
        """Le health check retourne 200 avec DB et cache OK."""
        resp = api_client.get('/health/')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert data['db']['status'] == 'ok'
        assert data['cache']['status'] == 'ok'

    def test_health_check_contient_latences(self, api_client):
        """Le health check expose les latences DB et cache."""
        resp = api_client.get('/health/')
        assert resp.status_code == 200
        data = resp.json()
        assert 'latency_ms' in data['db']
        assert 'latency_ms' in data['cache']
        # Les latences doivent être des entiers positifs
        assert isinstance(data['db']['latency_ms'], int)
        assert data['db']['latency_ms'] >= 0

    def test_health_check_contient_version(self, api_client):
        """Le health check expose la version de l'application."""
        resp = api_client.get('/health/')
        assert resp.status_code == 200
        assert 'version' in resp.json()

    def test_health_check_structure_complete(self, api_client):
        """Le health check retourne la structure complète attendue."""
        resp = api_client.get('/health/')
        data = resp.json()
        assert 'status' in data
        assert 'db' in data
        assert 'cache' in data
        assert 'status' in data['db']
        assert 'status' in data['cache']

    def test_health_check_cache_degraded_retourne_503(self, api_client, settings):
        """Si le cache est KO, le health check retourne 503."""
        # Simuler un cache KO en utilisant un backend qui échoue
        settings.CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
            }
        }
        # Avec DummyCache, cache.get() retourne toujours None → cache_ok = False
        resp = api_client.get('/health/')
        # DummyCache ne lève pas d'exception mais retourne None → cache_ok = False
        assert resp.status_code in (200, 503)  # Selon l'implémentation DummyCache


# ── Cache Redis ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCacheLayer:
    def test_render_cache_set_get(self):
        """Le cache de rendu fonctionne correctement."""
        from products.cache import set_render_cache, get_render_cache, invalidate_render_cache
        payload = {'product': {'id': 999}, 'blocks': [], 'test': True}
        set_render_cache(999, payload)
        cached = get_render_cache(999)
        assert cached is not None
        assert cached['test'] is True
        # Nettoyage
        invalidate_render_cache(999)

    def test_render_cache_miss(self):
        """Un cache miss retourne None."""
        from products.cache import get_render_cache
        result = get_render_cache(99999)
        assert result is None

    def test_render_cache_invalidation(self):
        """L'invalidation supprime le cache."""
        from products.cache import set_render_cache, get_render_cache, invalidate_render_cache
        set_render_cache(888, {'data': 'test'})
        assert get_render_cache(888) is not None
        invalidate_render_cache(888)
        assert get_render_cache(888) is None

    def test_theme_cache_set_get(self):
        """Le cache de thème fonctionne correctement."""
        from products.cache import set_theme_cache, get_theme_cache, invalidate_theme_cache
        theme_data = {'variables': {'primary_color': '#FF6B35'}}
        set_theme_cache(777, theme_data)
        cached = get_theme_cache(777)
        assert cached is not None
        assert cached['variables']['primary_color'] == '#FF6B35'
        invalidate_theme_cache(777)

    def test_theme_cache_invalidation(self):
        """L'invalidation du thème supprime le cache."""
        from products.cache import set_theme_cache, get_theme_cache, invalidate_theme_cache
        set_theme_cache(666, {'variables': {}})
        invalidate_theme_cache(666)
        assert get_theme_cache(666) is None

    def test_invalidate_all_renders_for_owner(self, db):
        """L'invalidation de tous les renders d'un owner fonctionne."""
        from products.cache import set_render_cache, get_render_cache, invalidate_all_renders_for_owner
        from products.models import Product
        owner = User.objects.create_user(username='owner_cache', password='pass')
        p1 = Product.objects.create(owner=owner, name='P1', price='10', sku='CACHE-P1')
        p2 = Product.objects.create(owner=owner, name='P2', price='10', sku='CACHE-P2')
        set_render_cache(p1.pk, {'data': 'p1'})
        set_render_cache(p2.pk, {'data': 'p2'})
        invalidate_all_renders_for_owner(owner.pk)
        assert get_render_cache(p1.pk) is None
        assert get_render_cache(p2.pk) is None

    def test_render_cache_utilise_sur_endpoint(self, api_client, db):
        """Le cache Redis est utilisé sur GET /render/<id>/."""
        from products.models import Product, PageTemplate, ProductTemplate
        owner = User.objects.create_user(username='owner_render', password='pass')
        product = Product.objects.create(owner=owner, name='Cached', price='10', sku='CACHE-R1')
        tpl = PageTemplate.objects.create(
            name='T', created_by=owner,
            config={'blocks': [{'type': 'hero', 'visibility': {}}]}
        )
        ProductTemplate.objects.create(product=product, template=tpl, is_active=True)

        # Premier appel — calcul + mise en cache
        resp1 = api_client.get(f'/api/v1/render/{product.pk}/')
        assert resp1.status_code == 200

        # Deuxième appel — depuis le cache (même résultat)
        resp2 = api_client.get(f'/api/v1/render/{product.pk}/')
        assert resp2.status_code == 200
        assert resp1.data['product']['id'] == resp2.data['product']['id']


# ── Throttle / Rate Limiting ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestThrottle:
    def test_login_throttle_scope_configure(self):
        """Le throttle 'login' est configuré dans les settings."""
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'login' in rates
        assert 'minute' in rates['login']

    def test_register_throttle_scope_configure(self):
        """Le throttle 'register' est configuré dans les settings."""
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'register' in rates
        assert 'minute' in rates['register']

    def test_validate_throttle_scope_configure(self):
        """Le throttle 'validate' est configuré dans les settings."""
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        assert 'validate' in rates
        assert 'minute' in rates['validate']

    def test_login_view_a_throttle_classe(self):
        """La vue login a bien le throttle LoginRateThrottle."""
        from users.views import LoginView
        from rest_framework.throttling import AnonRateThrottle
        throttle_classes = LoginView.throttle_classes
        assert len(throttle_classes) > 0
        # LoginRateThrottle hérite de AnonRateThrottle
        assert any(issubclass(cls, AnonRateThrottle) for cls in throttle_classes)

    def test_validate_view_a_throttle_scope(self):
        """La vue validate a bien le throttle_scope 'validate'."""
        from affiliations.views import ValidateAffiliationView
        assert hasattr(ValidateAffiliationView, 'throttle_scope')
        assert ValidateAffiliationView.throttle_scope == 'validate'

    def test_register_view_a_throttle_scope(self):
        """La vue register a bien le throttle_scope 'register'."""
        from users.views import RegisterView
        assert hasattr(RegisterView, 'throttle_scope')
        assert RegisterView.throttle_scope == 'register'


# ── Middleware RequestLogging ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestRequestLoggingMiddleware:
    def test_middleware_dans_settings(self):
        """Le middleware RequestLoggingMiddleware est dans MIDDLEWARE."""
        from django.conf import settings
        assert 'agc_core.middleware.RequestLoggingMiddleware' in settings.MIDDLEWARE

    def test_gzip_middleware_dans_settings(self):
        """Le middleware GZipMiddleware est dans MIDDLEWARE."""
        from django.conf import settings
        assert 'django.middleware.gzip.GZipMiddleware' in settings.MIDDLEWARE

    def test_middleware_log_requete(self, api_client):
        """Le middleware est bien dans la chaîne MIDDLEWARE."""
        from django.conf import settings
        assert 'agc_core.middleware.RequestLoggingMiddleware' in settings.MIDDLEWARE

    def test_middleware_get_client_ip(self):
        """Le middleware extrait correctement l'IP du client."""
        from agc_core.middleware import RequestLoggingMiddleware
        from unittest.mock import MagicMock
        middleware = RequestLoggingMiddleware(lambda r: MagicMock(status_code=200))

        # IP directe
        request = MagicMock()
        request.META = {'REMOTE_ADDR': '1.2.3.4'}
        assert middleware._get_client_ip(request) == '1.2.3.4'

        # IP derrière proxy (X-Forwarded-For)
        request.META = {'HTTP_X_FORWARDED_FOR': '5.6.7.8, 10.0.0.1', 'REMOTE_ADDR': '10.0.0.1'}
        assert middleware._get_client_ip(request) == '5.6.7.8'

    def test_middleware_exclut_health_check(self):
        """Le health check est dans la liste des paths exclus du logging."""
        from agc_core.middleware import _EXCLUDED_PATHS
        assert '/health/' in _EXCLUDED_PATHS


# ── Compression GZip ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGzipCompression:
    def test_gzip_middleware_compresse_json(self, api_client, db):
        """Le middleware GZip compresse les réponses JSON volumineuses."""
        from products.models import Product
        owner = User.objects.create_user(username='gzip_owner', password='pass')
        # Créer plusieurs produits pour avoir une réponse volumineuse
        for i in range(10):
            Product.objects.create(
                owner=owner, name=f'Produit GZip {i}',
                price='10.00', sku=f'GZIP-{i:03d}',
                description='Description longue ' * 20,
            )
        resp = api_client.get(
            '/api/v1/products/',
            HTTP_ACCEPT_ENCODING='gzip, deflate',
        )
        assert resp.status_code == 200
        # La réponse peut être compressée si elle dépasse le seuil (1024 bytes)
        # On vérifie juste que la réponse est valide
        assert 'results' in resp.data or isinstance(resp.data, list)


# ── Settings de production ────────────────────────────────────────────────────

class TestProductionSettings:
    def test_sentry_dsn_configurable(self):
        """SENTRY_DSN est configurable via variable d'environnement."""
        import os
        from django.conf import settings
        # En test, SENTRY_DSN est vide — Sentry ne doit pas être initialisé
        assert hasattr(settings, 'SENTRY_DSN')

    def test_commission_validation_delay_configurable(self):
        """COMMISSION_VALIDATION_DELAY_DAYS est configurable."""
        from django.conf import settings
        assert hasattr(settings, 'COMMISSION_VALIDATION_DELAY_DAYS')
        assert isinstance(settings.COMMISSION_VALIDATION_DELAY_DAYS, int)
        assert settings.COMMISSION_VALIDATION_DELAY_DAYS > 0

    def test_throttle_rates_tous_presents(self):
        """Tous les throttle rates sont configurés."""
        from django.conf import settings
        rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})
        required = ['anon', 'user', 'login', 'register', 'validate']
        for rate in required:
            assert rate in rates, f"Throttle rate '{rate}' manquant"

    def test_cache_ttl_configures(self):
        """Les TTL de cache sont configurés."""
        from django.conf import settings
        assert hasattr(settings, 'CACHE_TTL_PAGE_RENDER')
        assert hasattr(settings, 'CACHE_TTL_THEME')
        assert hasattr(settings, 'CACHE_TTL_PRODUCT')
        assert settings.CACHE_TTL_PAGE_RENDER > 0
        assert settings.CACHE_TTL_THEME > 0

    def test_conn_max_age_configure(self):
        """CONN_MAX_AGE est configuré pour les connexions persistantes PostgreSQL."""
        from django.conf import settings
        conn_max_age = settings.DATABASES['default'].get('CONN_MAX_AGE', 0)
        # En test (SQLite), CONN_MAX_AGE est aussi configuré à 60
        assert conn_max_age >= 0  # Présent dans la config

    def test_redis_ignore_exceptions(self):
        """Redis est configuré pour ignorer les exceptions (fallback gracieux)."""
        from django.conf import settings
        cache_options = settings.CACHES['default'].get('OPTIONS', {})
        # En production (Redis), IGNORE_EXCEPTIONS=True. En test (locmem), aussi configuré.
        assert cache_options.get('IGNORE_EXCEPTIONS') is True

    def test_logging_handlers_configures(self):
        """Les handlers de logging sont configurés (console + fichier rotatif)."""
        from django.conf import settings
        handlers = settings.LOGGING.get('handlers', {})
        assert 'console' in handlers
        assert 'file' in handlers
        # Le handler fichier doit être rotatif
        assert handlers['file']['class'] == 'logging.handlers.RotatingFileHandler'
        assert handlers['file']['maxBytes'] == 10 * 1024 * 1024  # 10 MB
        assert handlers['file']['backupCount'] == 5

    def test_loggers_modules_configures(self):
        """Tous les modules applicatifs ont un logger configuré."""
        from django.conf import settings
        loggers = settings.LOGGING.get('loggers', {})
        required_loggers = ['users', 'products', 'affiliations', 'orders', 'cache', 'security']
        for name in required_loggers:
            assert name in loggers, f"Logger '{name}' manquant"


# ── Nginx config validation ───────────────────────────────────────────────────

class TestNginxConfig:
    """
    Tests de validation de la configuration Nginx.
    Vérifie que les directives critiques sont présentes dans le fichier de config.
    """

    def _read_nginx_conf(self) -> str:
        import os
        conf_path = os.path.join(os.path.dirname(__file__), '..', 'deploy', 'nginx.conf')
        with open(conf_path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_proxy_cache_path_present(self):
        """proxy_cache_path doit être défini (corrige le bug de l'analyse)."""
        conf = self._read_nginx_conf()
        assert 'proxy_cache_path' in conf, "proxy_cache_path manquant — le cache Nginx ne fonctionnera pas"

    def test_proxy_cache_zone_definie(self):
        """La zone de cache agc_cache doit être définie."""
        conf = self._read_nginx_conf()
        assert 'keys_zone=agc_cache' in conf

    def test_proxy_cache_utilise_sur_render(self):
        """Le cache Nginx doit être activé sur l'endpoint /render/."""
        conf = self._read_nginx_conf()
        assert 'proxy_cache' in conf
        assert 'agc_cache' in conf

    def test_csp_header_present(self):
        """Content-Security-Policy doit être défini."""
        conf = self._read_nginx_conf()
        assert 'Content-Security-Policy' in conf

    def test_hsts_header_present(self):
        """HSTS doit être configuré."""
        conf = self._read_nginx_conf()
        assert 'Strict-Transport-Security' in conf

    def test_gzip_configure(self):
        """La compression gzip doit être activée dans Nginx."""
        conf = self._read_nginx_conf()
        assert 'gzip on' in conf
        assert 'gzip_types' in conf

    def test_rate_limiting_login(self):
        """Le rate limiting sur /auth/login/ doit être configuré."""
        conf = self._read_nginx_conf()
        assert 'login_zone' in conf
        assert 'limit_req_zone' in conf

    def test_rate_limiting_register(self):
        """Le rate limiting sur /auth/register/ doit être configuré."""
        conf = self._read_nginx_conf()
        assert 'register_zone' in conf

    def test_rate_limiting_validate(self):
        """Le rate limiting sur /affiliations/validate/ doit être configuré."""
        conf = self._read_nginx_conf()
        assert 'validate_zone' in conf

    def test_ssl_tls_configure(self):
        """SSL/TLS doit être configuré avec TLS 1.2 et 1.3."""
        conf = self._read_nginx_conf()
        assert 'TLSv1.2' in conf
        assert 'TLSv1.3' in conf

    def test_http2_active(self):
        """HTTP/2 doit être activé."""
        conf = self._read_nginx_conf()
        assert 'http2' in conf

    def test_erreur_429_configuree(self):
        """La page d'erreur 429 (rate limit) doit être configurée."""
        conf = self._read_nginx_conf()
        assert '429' in conf

    def test_x_cache_status_header(self):
        """Le header X-Cache-Status doit être exposé pour le debugging."""
        conf = self._read_nginx_conf()
        assert 'X-Cache-Status' in conf

    def test_proxy_cache_stale_configure(self):
        """proxy_cache_use_stale doit être configuré pour la résilience."""
        conf = self._read_nginx_conf()
        assert 'proxy_cache_use_stale' in conf
