# Auteur : Gilles - Projet : AGC Space - Module : Products - Tests
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def ecommercant(db):
    from users.models import Role
    user = User.objects.create_user(username='vendeur', password='pass', email='v@test.com')
    user.add_role(Role.ECOMMERCANT)
    return user


@pytest.fixture
def auth_client(api_client, ecommercant):
    api_client.force_authenticate(user=ecommercant)
    return api_client


@pytest.fixture
def product(ecommercant):
    from products.models import Product
    return Product.objects.create(
        owner=ecommercant, name='Formation Django',
        price='97.00', sku='FORM-DJG-001', is_digital=True, stock=10,
    )


@pytest.fixture
def theme(ecommercant):
    from products.models import Theme
    return Theme.objects.create(
        owner=ecommercant,
        name='Thème Test',
        variables={
            'primary_color': '#FF6B35',
            'font_family': 'Inter, sans-serif',
            'border_radius': '8px',
        }
    )


@pytest.fixture
def template_with_blocks(ecommercant, product):
    from products.models import PageTemplate, ProductTemplate
    config = {
        'blocks': [
            {'type': 'hero', 'text': 'Titre', 'visibility': {}},
            {'type': 'social_proof', 'mode': 'sales_count', 'visibility': {}},
            {'type': 'countdown', 'duration_hours': 24, 'visibility': {}},
            {'type': 'stock_status', 'visibility': {'stock_min': 1}},
            {'type': 'buy_button', 'label': 'Acheter', 'affiliate_aware': True, 'visibility': {'stock_min': 1}},
        ]
    }
    tpl = PageTemplate.objects.create(name='Template Smart', config=config, created_by=ecommercant)
    ProductTemplate.objects.create(product=product, template=tpl, is_active=True)
    return tpl


# ── Modèle Theme ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTheme:
    def test_creation_theme(self, ecommercant):
        from products.models import Theme
        theme = Theme.objects.create(
            owner=ecommercant,
            variables={'primary_color': '#FF6B35', 'font_family': 'Inter'}
        )
        assert theme.pk is not None

    def test_to_css_variables(self, theme):
        css = theme.to_css_variables()
        assert ':root' in css
        assert '--primary-color' in css
        assert '#FF6B35' in css

    def test_variables_vides(self, ecommercant):
        from products.models import Theme
        theme = Theme.objects.create(owner=ecommercant, variables={})
        assert theme.to_css_variables() == ':root {}'


# ── Modèle PageTemplate + Critical CSS ───────────────────────────────────────

@pytest.mark.django_db
class TestPageTemplate:
    def test_critical_css_genere_au_save(self, ecommercant):
        from products.models import PageTemplate
        tpl = PageTemplate.objects.create(
            name='T', created_by=ecommercant,
            config={'blocks': [{'type': 'hero'}, {'type': 'buy_button'}]}
        )
        assert '.block-hero' in tpl.critical_css
        assert '.block-buy-button' in tpl.critical_css

    def test_critical_css_lazy_par_type(self, ecommercant):
        from products.models import PageTemplate
        tpl = PageTemplate.objects.create(
            name='T2', created_by=ecommercant,
            config={'blocks': [{'type': 'countdown'}]}
        )
        assert '.block-countdown' in tpl.critical_css
        # Les blocs absents ne doivent pas générer de CSS
        assert '.block-hero' not in tpl.critical_css

    def test_critical_css_avec_theme(self, ecommercant, theme):
        from products.models import PageTemplate
        tpl = PageTemplate.objects.create(
            name='T3', created_by=ecommercant,
            config={'blocks': [{'type': 'hero'}]}
        )
        assert '--primary-color' in tpl.critical_css

    def test_template_reutilisable(self, ecommercant):
        from products.models import Product, PageTemplate, ProductTemplate
        tpl = PageTemplate.objects.create(
            name='Shared', config={'blocks': []}, created_by=ecommercant
        )
        for i in range(3):
            p = Product.objects.create(owner=ecommercant, name=f'P{i}', price='10', sku=f'SKU-{i}')
            ProductTemplate.objects.create(product=p, template=tpl)
        assert tpl.products.count() == 3


# ── Services ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestServices:
    def test_social_proof_sans_ventes(self, product):
        from products.services import get_social_proof_data
        data = get_social_proof_data(product)
        assert data['total_sold'] == 0
        assert data['buyer_count'] == 0

    def test_countdown_non_expire(self, product):
        from products.services import get_countdown_data
        data = get_countdown_data(product, duration_hours=9999)
        assert data['seconds_remaining'] > 0
        assert data['is_expired'] is False

    def test_countdown_expire(self, product):
        from products.services import get_countdown_data
        data = get_countdown_data(product, duration_hours=0)
        assert data['is_expired'] is True

    def test_stock_status_ok(self, product):
        from products.services import get_stock_status_data
        product.stock = 10
        data = get_stock_status_data(product)
        assert data['level'] == 'ok'

    def test_stock_status_low(self, product):
        from products.services import get_stock_status_data
        product.stock = 3
        data = get_stock_status_data(product)
        assert data['level'] == 'low'

    def test_stock_status_out(self, product):
        from products.services import get_stock_status_data
        product.stock = 0
        data = get_stock_status_data(product)
        assert data['level'] == 'out'

    def test_visibilite_stock_min_masque(self, product):
        from products.services import evaluate_block_visibility
        product.stock = 0
        block = {'type': 'buy_button', 'visibility': {'stock_min': 1}}
        assert evaluate_block_visibility(block, product) is False

    def test_visibilite_stock_min_affiche(self, product):
        from products.services import evaluate_block_visibility
        product.stock = 5
        block = {'type': 'buy_button', 'visibility': {'stock_min': 1}}
        assert evaluate_block_visibility(block, product) is True

    def test_enrich_blocks_filtre_visibilite(self, product):
        from products.services import enrich_blocks
        product.stock = 0
        blocks = [
            {'type': 'hero', 'visibility': {}},
            {'type': 'buy_button', 'visibility': {'stock_min': 1}},
        ]
        enriched = enrich_blocks(blocks, product)
        types = [b['type'] for b in enriched]
        assert 'hero' in types
        assert 'buy_button' not in types

    def test_enrich_blocks_injecte_donnees(self, product):
        from products.services import enrich_blocks
        blocks = [
            {'type': 'social_proof', 'visibility': {}},
            {'type': 'countdown', 'duration_hours': 24, 'visibility': {}},
            {'type': 'stock_status', 'visibility': {}},
        ]
        enriched = enrich_blocks(blocks, product)
        types = {b['type']: b for b in enriched}
        assert 'data' in types['social_proof']
        assert 'data' in types['countdown']
        assert 'data' in types['stock_status']

    def test_validate_block_type_inconnu(self):
        from products.services import validate_block_structure
        errors = validate_block_structure({'type': 'unknown_block'})
        assert len(errors) > 0

    def test_validate_block_sans_type(self):
        from products.services import validate_block_structure
        errors = validate_block_structure({})
        assert len(errors) > 0

    def test_validate_block_valide(self):
        from products.services import validate_block_structure
        errors = validate_block_structure({'type': 'hero', 'visibility': {}})
        assert errors == []


# ── Serializers ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestThemeSerializer:
    def test_variables_inconnues_rejetees(self, ecommercant):
        from products.serializers import ThemeSerializer
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        req = factory.post('/')
        req.user = ecommercant
        s = ThemeSerializer(data={'name': 'T', 'variables': {'unknown_var': 'red'}}, context={'request': req})
        assert not s.is_valid()
        assert 'variables' in s.errors

    def test_variables_valides(self, ecommercant):
        from products.serializers import ThemeSerializer
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        req = factory.post('/')
        req.user = ecommercant
        s = ThemeSerializer(
            data={'name': 'T', 'variables': {'primary_color': '#FF6B35'}},
            context={'request': req}
        )
        assert s.is_valid(), s.errors


@pytest.mark.django_db
class TestPageTemplateSerializer:
    def test_config_sans_blocks_rejetee(self, ecommercant):
        from products.serializers import PageTemplateSerializer
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        req = factory.post('/')
        req.user = ecommercant
        s = PageTemplateSerializer(
            data={'name': 'T', 'config': {'no_blocks': True}},
            context={'request': req}
        )
        assert not s.is_valid()

    def test_bloc_type_inconnu_rejete(self, ecommercant):
        from products.serializers import PageTemplateSerializer
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        req = factory.post('/')
        req.user = ecommercant
        s = PageTemplateSerializer(
            data={'name': 'T', 'config': {'blocks': [{'type': 'invalid_type'}]}},
            context={'request': req}
        )
        assert not s.is_valid()

    def test_config_valide(self, ecommercant):
        from products.serializers import PageTemplateSerializer
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        req = factory.post('/')
        req.user = ecommercant
        s = PageTemplateSerializer(
            data={'name': 'T', 'config': {'blocks': [{'type': 'hero', 'visibility': {}}]}},
            context={'request': req}
        )
        assert s.is_valid(), s.errors


# ── API Views ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestThemeAPI:
    def test_get_or_create_theme(self, auth_client):
        resp = auth_client.get('/api/v1/themes/mine/')
        assert resp.status_code == 200
        assert 'variables' in resp.data
        assert 'css_preview' in resp.data

    def test_update_theme(self, auth_client):
        resp = auth_client.post('/api/v1/themes/', {
            'name': 'Mon thème',
            'variables': {'primary_color': '#123456'},
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['variables']['primary_color'] == '#123456'


@pytest.mark.django_db
class TestPageRenderAPI:
    def test_render_payload_complet(self, api_client, product, template_with_blocks):
        resp = api_client.get(f'/api/v1/render/{product.pk}/')
        assert resp.status_code == 200
        assert 'product' in resp.data
        assert 'blocks' in resp.data
        assert 'critical_css' in resp.data
        assert 'theme' in resp.data
        assert 'meta' in resp.data

    def test_render_blocs_enrichis(self, api_client, product, template_with_blocks):
        resp = api_client.get(f'/api/v1/render/{product.pk}/')
        assert resp.status_code == 200
        block_types = [b['type'] for b in resp.data['blocks']]
        assert 'social_proof' in block_types
        assert 'countdown' in block_types

    def test_render_blocs_avec_donnees_injectees(self, api_client, product, template_with_blocks):
        resp = api_client.get(f'/api/v1/render/{product.pk}/')
        blocks_by_type = {b['type']: b for b in resp.data['blocks']}
        assert 'data' in blocks_by_type['social_proof']
        assert 'data' in blocks_by_type['countdown']
        assert 'seconds_remaining' in blocks_by_type['countdown']['data']

    def test_render_visibilite_stock_zero(self, api_client, ecommercant):
        from products.models import Product, PageTemplate, ProductTemplate
        p = Product.objects.create(
            owner=ecommercant, name='Rupture', price='10', sku='RUPTURE-001', stock=0
        )
        tpl = PageTemplate.objects.create(
            name='T', created_by=ecommercant,
            config={'blocks': [
                {'type': 'hero', 'visibility': {}},
                {'type': 'buy_button', 'visibility': {'stock_min': 1}},
            ]}
        )
        ProductTemplate.objects.create(product=p, template=tpl, is_active=True)
        resp = api_client.get(f'/api/v1/render/{p.pk}/')
        block_types = [b['type'] for b in resp.data['blocks']]
        assert 'hero' in block_types
        assert 'buy_button' not in block_types

    def test_render_meta_tracking(self, api_client, product, template_with_blocks):
        resp = api_client.get(f'/api/v1/render/{product.pk}/')
        meta = resp.data['meta']
        assert 'tracking_events' in meta
        assert 'affiliate_aware_blocks' in meta
        assert 'buy_button' in meta['affiliate_aware_blocks']

    def test_render_critical_css_non_vide(self, api_client, product, template_with_blocks):
        resp = api_client.get(f'/api/v1/render/{product.pk}/')
        assert len(resp.data['critical_css']) > 0

    def test_render_sans_template_404(self, api_client, ecommercant):
        from products.models import Product
        p = Product.objects.create(
            owner=ecommercant, name='Sans template', price='10', sku='NO-TPL-001'
        )
        resp = api_client.get(f'/api/v1/render/{p.pk}/')
        assert resp.status_code == 404

    def test_render_produit_inactif_404(self, api_client, ecommercant):
        from products.models import Product
        p = Product.objects.create(
            owner=ecommercant, name='Inactif', price='10', sku='INACT-001', is_active=False
        )
        resp = api_client.get(f'/api/v1/render/{p.pk}/')
        assert resp.status_code == 404


@pytest.mark.django_db
class TestProductAPI:
    def test_create_product(self, auth_client):
        resp = auth_client.post('/api/v1/products/', {
            'name': 'Nouveau', 'price': '49.00', 'sku': 'NEW-001', 'is_digital': True,
        })
        assert resp.status_code == 201

    def test_template_css_endpoint(self, auth_client, template_with_blocks):
        resp = auth_client.get(f'/api/v1/templates/{template_with_blocks.pk}/css/')
        assert resp.status_code == 200
        assert 'critical_css' in resp.data

    def test_create_product_sku_auto_genere(self, auth_client):
        """Un produit sans SKU reçoit un SKU auto-généré."""
        resp = auth_client.post('/api/v1/products/', {
            'name': 'Sans SKU', 'price': '29.00',
        })
        assert resp.status_code == 201
        assert resp.data['sku'].startswith('AGC-')

    def test_create_product_prix_negatif_rejete(self, auth_client):
        """Un prix négatif ou nul doit être rejeté."""
        resp = auth_client.post('/api/v1/products/', {
            'name': 'Prix invalide', 'price': '-10.00', 'sku': 'NEG-001',
        })
        assert resp.status_code == 400

    def test_create_product_prix_zero_rejete(self, auth_client):
        resp = auth_client.post('/api/v1/products/', {
            'name': 'Prix zéro', 'price': '0.00', 'sku': 'ZERO-001',
        })
        assert resp.status_code == 400

    def test_create_product_stock_negatif_rejete(self, auth_client):
        resp = auth_client.post('/api/v1/products/', {
            'name': 'Stock négatif', 'price': '10.00', 'sku': 'NEGSTOCK-001', 'stock': -5,
        })
        assert resp.status_code == 400

    def test_list_products_pagine(self, auth_client, ecommercant):
        """La liste des produits est paginée."""
        from products.models import Product
        for i in range(5):
            Product.objects.create(
                owner=ecommercant, name=f'Produit {i}', price='10.00', sku=f'PAG-{i}'
            )
        resp = auth_client.get('/api/v1/products/')
        assert resp.status_code == 200
        # Réponse paginée : contient count, next, previous, results
        assert 'count' in resp.data
        assert 'results' in resp.data

    def test_list_products_search(self, auth_client, ecommercant):
        """La recherche filtre par nom."""
        from products.models import Product
        Product.objects.create(owner=ecommercant, name='Formation Python', price='97.00', sku='PY-001')
        Product.objects.create(owner=ecommercant, name='Coaching SEO', price='197.00', sku='SEO-001')
        resp = auth_client.get('/api/v1/products/?search=Python')
        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert 'Formation Python' in names
        assert 'Coaching SEO' not in names

    def test_list_products_filtre_categorie(self, auth_client, ecommercant):
        """Le filtre par catégorie fonctionne (insensible à la casse)."""
        from products.models import Product
        Product.objects.create(owner=ecommercant, name='Prod Formation', price='97.00',
                               sku='CAT-001', category='Formation')
        Product.objects.create(owner=ecommercant, name='Prod SaaS', price='49.00',
                               sku='CAT-002', category='SaaS')
        resp = auth_client.get('/api/v1/products/?category=formation')
        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert 'Prod Formation' in names
        assert 'Prod SaaS' not in names

    def test_list_products_filtre_prix(self, auth_client, ecommercant):
        """Le filtre par fourchette de prix fonctionne."""
        from products.models import Product
        Product.objects.create(owner=ecommercant, name='Pas cher', price='9.00', sku='CHEAP-001')
        Product.objects.create(owner=ecommercant, name='Cher', price='999.00', sku='EXP-001')
        resp = auth_client.get('/api/v1/products/?min_price=50&max_price=500')
        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert 'Pas cher' not in names
        assert 'Cher' not in names

    def test_list_products_filtre_digital(self, auth_client, ecommercant):
        """Le filtre is_digital fonctionne."""
        from products.models import Product
        Product.objects.create(owner=ecommercant, name='Digital', price='97.00',
                               sku='DIG-F-001', is_digital=True)
        Product.objects.create(owner=ecommercant, name='Physique', price='49.00',
                               sku='PHY-F-001', is_digital=False)
        resp = auth_client.get('/api/v1/products/?is_digital=true')
        assert resp.status_code == 200
        names = [p['name'] for p in resp.data['results']]
        assert 'Digital' in names
        assert 'Physique' not in names

    def test_list_products_ordering(self, auth_client, ecommercant):
        """Le tri par prix fonctionne."""
        from products.models import Product
        Product.objects.create(owner=ecommercant, name='Moyen', price='50.00', sku='ORD-002')
        Product.objects.create(owner=ecommercant, name='Moins cher', price='10.00', sku='ORD-001')
        resp = auth_client.get('/api/v1/products/?ordering=price')
        assert resp.status_code == 200
        prices = [float(p['price']) for p in resp.data['results']]
        assert prices == sorted(prices)

    def test_produit_autre_vendeur_non_modifiable(self, api_client, ecommercant):
        """Un vendeur ne peut pas modifier le produit d'un autre vendeur.
        DRF retourne 404 car le produit n'est pas dans son queryset (filtre owner)."""
        from products.models import Product
        from django.contrib.auth import get_user_model
        User = get_user_model()
        autre = User.objects.create_user(username='autre_vendeur', password='pass')
        produit_autre = Product.objects.create(
            owner=autre, name='Produit Autre', price='50.00', sku='AUTRE-001'
        )
        api_client.force_authenticate(user=ecommercant)
        resp = api_client.patch(f'/api/v1/products/{produit_autre.pk}/', {'price': '1.00'})
        # DRF retourne 404 (pas dans le queryset) plutôt que 403 — comportement attendu
        assert resp.status_code in (403, 404)

    def test_produit_non_authentifie_lecture_ok(self, api_client, product, template_with_blocks):
        """Un utilisateur non authentifié peut lire la liste des produits actifs."""
        resp = api_client.get('/api/v1/products/')
        assert resp.status_code == 200


# ── Tests Upload ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFileUpload:
    def test_upload_sans_fichier(self, auth_client):
        resp = auth_client.post('/api/v1/upload/', {})
        assert resp.status_code == 400
        assert 'error' in resp.data

    def test_upload_extension_invalide(self, auth_client):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile('script.exe', b'MZ\x90\x00', content_type='application/octet-stream')
        resp = auth_client.post('/api/v1/upload/', {'file': fake_file}, format='multipart')
        assert resp.status_code == 400
        assert 'error' in resp.data

    def test_upload_image_valide(self, auth_client):
        """Upload d'une vraie image PNG (1x1 pixel)."""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Créer une vraie image PNG en mémoire
        img_io = io.BytesIO()
        Image.new('RGB', (1, 1), color='red').save(img_io, format='PNG')
        img_io.seek(0)
        fake_img = SimpleUploadedFile('test.png', img_io.read(), content_type='image/png')
        resp = auth_client.post('/api/v1/upload/', {'file': fake_img}, format='multipart')
        assert resp.status_code == 201
        assert resp.data['type'] == 'image'
        assert 'url' in resp.data

    def test_upload_non_authentifie(self, api_client):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile('test.png', b'fake', content_type='image/png')
        resp = api_client.post('/api/v1/upload/', {'file': fake_file}, format='multipart')
        assert resp.status_code == 401


# ── Tests VendeurStats ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVendeurStats:
    def test_stats_vendeur_vide(self, auth_client):
        """Stats d'un vendeur sans produits ni commandes."""
        resp = auth_client.get('/api/v1/dashboard/stats/')
        assert resp.status_code == 200
        assert resp.data['total_revenue'] == '0.00'
        assert resp.data['active_products_count'] == 0
        assert resp.data['active_affiliates_count'] == 0

    def test_stats_vendeur_avec_produits(self, auth_client, product):
        """Stats avec un produit actif."""
        resp = auth_client.get('/api/v1/dashboard/stats/')
        assert resp.status_code == 200
        assert resp.data['active_products_count'] == 1
        assert resp.data['top_product'] is not None
        assert resp.data['top_product']['name'] == product.name

    def test_stats_non_authentifie(self, api_client):
        resp = api_client.get('/api/v1/dashboard/stats/')
        assert resp.status_code == 401


# ── Tests BuilderInit ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuilderInit:
    def test_builder_init_cree_template_par_defaut(self, auth_client, product):
        """BuilderInit crée un template par défaut si le produit n'en a pas."""
        from products.models import ProductTemplate
        assert ProductTemplate.objects.filter(product=product).count() == 0
        resp = auth_client.get(f'/api/v1/builder/{product.pk}/init/')
        assert resp.status_code == 200
        assert 'template' in resp.data
        assert 'blocks' in resp.data
        assert ProductTemplate.objects.filter(product=product).count() == 1

    def test_builder_init_reutilise_template_existant(self, auth_client, product, template_with_blocks):
        """BuilderInit réutilise le template actif existant."""
        from products.models import ProductTemplate
        count_avant = ProductTemplate.objects.filter(product=product).count()
        resp = auth_client.get(f'/api/v1/builder/{product.pk}/init/')
        assert resp.status_code == 200
        assert ProductTemplate.objects.filter(product=product).count() == count_avant

    def test_builder_init_produit_autre_vendeur_interdit(self, api_client, ecommercant):
        """Un vendeur ne peut pas accéder au builder d'un produit qui ne lui appartient pas."""
        from products.models import Product
        from django.contrib.auth import get_user_model
        User = get_user_model()
        autre = User.objects.create_user(username='autre_v2', password='pass')
        produit_autre = Product.objects.create(
            owner=autre, name='Produit Autre', price='50.00', sku='AUTRE-B-001'
        )
        api_client.force_authenticate(user=ecommercant)
        resp = api_client.get(f'/api/v1/builder/{produit_autre.pk}/init/')
        assert resp.status_code == 404
