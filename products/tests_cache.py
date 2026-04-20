# Auteur : Gilles - Projet : AGC Space - Module : Products - Tests Cache Phase 4
"""
Tests du cache Redis pour les pages de vente et les thèmes.
Utilise le cache Django en mode locmem (pas besoin de Redis pour les tests).
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def ecommercant(db):
    from users.models import Role
    user = User.objects.create_user(username='vendeur_cache', password='pass')
    user.add_role(Role.ECOMMERCANT)
    return user


@pytest.fixture
def product_with_template(ecommercant):
    from products.models import Product, PageTemplate, ProductTemplate
    product = Product.objects.create(
        owner=ecommercant, name='Produit Cache Test',
        price='49.99', sku='CACHE-001', stock=10,
    )
    tpl = PageTemplate.objects.create(
        name='Template Cache',
        config={'blocks': [{'type': 'hero', 'visibility': {}}, {'type': 'buy_button', 'visibility': {}}]},
        created_by=ecommercant,
    )
    ProductTemplate.objects.create(product=product, template=tpl, is_active=True)
    return product


# ── Tests unitaires du module cache ──────────────────────────────────────────

class TestCacheModule:
    """Tests du module products/cache.py — sans DB, avec mock Django cache."""

    def test_get_render_cache_miss(self):
        from products.cache import get_render_cache
        with patch('products.cache.cache') as mock_cache:
            mock_cache.get.return_value = None
            result = get_render_cache(42)
            assert result is None
            mock_cache.get.assert_called_once()

    def test_get_render_cache_hit(self):
        from products.cache import get_render_cache
        payload = {'product': {'id': 42}, 'blocks': []}
        with patch('products.cache.cache') as mock_cache:
            mock_cache.get.return_value = payload
            result = get_render_cache(42)
            assert result == payload

    def test_set_render_cache(self):
        from products.cache import set_render_cache
        payload = {'product': {'id': 42}}
        with patch('products.cache.cache') as mock_cache:
            set_render_cache(42, payload)
            mock_cache.set.assert_called_once()
            args = mock_cache.set.call_args
            assert 'render:product:42' in args[0][0]

    def test_invalidate_render_cache(self):
        from products.cache import invalidate_render_cache
        with patch('products.cache.cache') as mock_cache:
            invalidate_render_cache(42)
            mock_cache.delete.assert_called_once()

    def test_set_cache_redis_down_ne_plante_pas(self):
        """Si Redis est down, set_render_cache ne doit pas lever d'exception."""
        from products.cache import set_render_cache
        with patch('products.cache.cache') as mock_cache:
            mock_cache.set.side_effect = Exception("Redis connection refused")
            # Ne doit pas lever d'exception
            set_render_cache(42, {'product': {}})

    def test_cles_differentes_par_produit(self):
        from products.cache import _key_render
        assert _key_render(1) != _key_render(2)
        assert '1' in _key_render(1)
        assert '2' in _key_render(2)

    def test_cle_theme_differente_par_user(self):
        from products.cache import _key_theme
        assert _key_theme(1) != _key_theme(2)


# ── Tests d'intégration API avec cache ───────────────────────────────────────

@pytest.mark.django_db
class TestPageRenderCache:
    """
    Tests de l'endpoint /render/ avec cache.
    Utilise le cache Django locmem (configuré dans pytest.ini via DJANGO_SETTINGS_MODULE).
    """

    def test_render_premier_appel_calcule(self, api_client, product_with_template):
        """Premier appel : cache miss → calcul complet."""
        from products.cache import invalidate_render_cache
        invalidate_render_cache(product_with_template.pk)

        resp = api_client.get(f'/api/v1/render/{product_with_template.pk}/')
        assert resp.status_code == 200
        assert 'blocks' in resp.data
        assert 'critical_css' in resp.data

    def test_render_deuxieme_appel_depuis_cache(self, api_client, product_with_template):
        """Deuxième appel : doit retourner le même payload."""
        from products.cache import invalidate_render_cache, set_render_cache, get_render_cache
        invalidate_render_cache(product_with_template.pk)

        # Premier appel
        resp1 = api_client.get(f'/api/v1/render/{product_with_template.pk}/')
        assert resp1.status_code == 200

        # Vérifier que le cache est rempli
        cached = get_render_cache(product_with_template.pk)
        assert cached is not None

        # Deuxième appel — même résultat
        resp2 = api_client.get(f'/api/v1/render/{product_with_template.pk}/')
        assert resp2.status_code == 200
        assert resp2.data['template']['id'] == resp1.data['template']['id']

    def test_invalidation_cache_apres_update_produit(self, api_client, ecommercant, product_with_template):
        """Modifier un produit doit invalider son cache de rendu."""
        from products.cache import get_render_cache, invalidate_render_cache
        invalidate_render_cache(product_with_template.pk)

        # Remplir le cache
        api_client.get(f'/api/v1/render/{product_with_template.pk}/')
        assert get_render_cache(product_with_template.pk) is not None

        # Modifier le produit via API
        auth_client = APIClient()
        auth_client.force_authenticate(user=ecommercant)
        auth_client.patch(
            f'/api/v1/products/{product_with_template.pk}/',
            {'price': '59.99'},
            format='json',
        )

        # Le cache doit être invalidé
        assert get_render_cache(product_with_template.pk) is None

    def test_render_produit_inexistant(self, api_client):
        resp = api_client.get('/api/v1/render/99999/')
        assert resp.status_code == 404


# ── Tests health check ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestHealthCheck:
    def test_health_endpoint_accessible(self, api_client):
        import json
        resp = api_client.get('/health/')
        assert resp.status_code in [200, 503]
        data = json.loads(resp.content)
        assert 'status' in data
        assert 'db' in data
        assert 'cache' in data

    def test_health_db_ok(self, api_client):
        import json
        resp = api_client.get('/health/')
        data = json.loads(resp.content)
        assert data['db'] == 'ok'
