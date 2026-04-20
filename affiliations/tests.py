# Auteur : Gilles - Projet : AGC Space - Module : Affiliations - Tests
import pytest
import time
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def vendeur(db):
    from users.models import Role
    user = User.objects.create_user(username='vendeur', password='pass')
    user.add_role(Role.ECOMMERCANT)
    return user


@pytest.fixture
def affilie(db):
    from users.models import Role
    user = User.objects.create_user(username='affilie', password='pass')
    user.add_role(Role.AFFILIE)
    return user


@pytest.fixture
def affilie2(db):
    from users.models import Role
    user = User.objects.create_user(username='affilie2', password='pass')
    user.add_role(Role.AFFILIE)
    return user


@pytest.fixture
def auth_affilie(api_client, affilie):
    api_client.force_authenticate(user=affilie)
    return api_client


@pytest.fixture
def auth_vendeur(api_client, vendeur):
    api_client.force_authenticate(user=vendeur)
    return api_client


@pytest.fixture
def product(vendeur):
    from products.models import Product
    return Product.objects.create(
        owner=vendeur, name='Produit Affiliation',
        price='50.00', sku='AFF-001', stock=10,
    )


@pytest.fixture
def product_with_max_rate(vendeur):
    from products.models import Product
    return Product.objects.create(
        owner=vendeur, name='Produit Taux Limité',
        price='100.00', sku='AFF-MAX-001', stock=5,
        max_commission_rate='0.2000',  # 20% max
    )


@pytest.fixture
def affiliation_link(product, affilie):
    from affiliations.models import AffiliationLink
    return AffiliationLink.objects.create(
        product=product, affiliate=affilie, commission_rate='0.1500'
    )


@pytest.fixture
def client_user(db):
    from users.models import Role
    user = User.objects.create_user(username='client', password='pass')
    user.add_role(Role.CLIENT)
    return user


# ── Modèle AffiliationLink ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAffiliationLinkModel:
    def test_creation_lien(self, affiliation_link):
        assert affiliation_link.tracking_code != ''
        assert affiliation_link.is_active is True

    def test_tracking_codes_uniques(self, product, affilie, affilie2):
        from affiliations.models import AffiliationLink
        l1 = AffiliationLink.objects.create(product=product, affiliate=affilie, commission_rate='0.10')
        l2 = AffiliationLink.objects.create(product=product, affiliate=affilie2, commission_rate='0.10')
        assert l1.tracking_code != l2.tracking_code

    def test_unicite_affilie_produit(self, product, affilie):
        from affiliations.models import AffiliationLink
        from django.db import IntegrityError
        AffiliationLink.objects.create(product=product, affiliate=affilie, commission_rate='0.10')
        with pytest.raises(IntegrityError):
            AffiliationLink.objects.create(product=product, affiliate=affilie, commission_rate='0.20')

    def test_clicks_count_initial_zero(self, affiliation_link):
        assert affiliation_link.clicks_count == 0

    def test_taux_max_absolu_refuse(self, product, affilie):
        """Un taux > 50% doit être refusé par le validateur du modèle."""
        from affiliations.models import AffiliationLink
        from django.core.exceptions import ValidationError
        link = AffiliationLink(product=product, affiliate=affilie, commission_rate='0.9999')
        with pytest.raises(ValidationError):
            link.full_clean()


# ── Modèle Commission ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCommissionModel:
    def test_creation_commission(self, affiliation_link, affilie):
        from affiliations.models import Commission
        from orders.models import Order
        client = User.objects.create_user(username='client_c', password='pass')
        order = Order.objects.create(customer=client, total='50.00', status='paid')
        commission = Commission.objects.create(
            order=order,
            affiliation_link=affiliation_link,
            affiliate=affilie,
            order_total='50.00',
            commission_rate='0.1500',
            amount='7.50',
        )
        assert commission.status == Commission.STATUS_PENDING
        assert str(commission.amount) == '7.50'

    def test_str_commission(self, affiliation_link, affilie):
        from affiliations.models import Commission
        from orders.models import Order
        client = User.objects.create_user(username='client2', password='pass')
        order = Order.objects.create(customer=client, total='100.00')
        c = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affilie,
            order_total='100.00', commission_rate='0.15', amount='15.00',
        )
        assert 'affilie' in str(c)
        assert '15.00' in str(c)

    def test_validated_at_renseigne_automatiquement(self, affiliation_link, affilie):
        """validated_at doit être renseigné automatiquement lors du passage en validated."""
        from affiliations.models import Commission
        from orders.models import Order
        client = User.objects.create_user(username='client_v', password='pass')
        order = Order.objects.create(customer=client, total='50.00')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affilie,
            order_total='50.00', commission_rate='0.15', amount='7.50',
        )
        assert commission.validated_at is None
        commission.status = Commission.STATUS_VALIDATED
        commission.save()
        assert commission.validated_at is not None


# ── Services HMAC ─────────────────────────────────────────────────────────────

class TestHMACServices:
    def test_generate_signed_url(self):
        from affiliations.services import generate_signed_url
        result = generate_signed_url('TRACK123', 42, 'http://localhost:8000/shop/42/')
        assert 'url' in result
        assert 'TRACK123' in result['url']
        assert 'sig=' in result['url']
        assert 'exp=' in result['url']
        assert result['expires_at'] > int(time.time())

    def test_verify_valid_signature(self):
        from affiliations.services import generate_signed_url, verify_signed_url
        result = generate_signed_url('TRACK123', 42, 'http://localhost:8000/')
        is_valid, reason = verify_signed_url('TRACK123', 42, result['signature'], result['expires_at'])
        assert is_valid is True
        assert reason == 'OK'

    def test_verify_mauvaise_signature(self):
        from affiliations.services import generate_signed_url, verify_signed_url
        result = generate_signed_url('TRACK123', 42, 'http://localhost:8000/')
        is_valid, reason = verify_signed_url('TRACK123', 42, 'fausse_signature', result['expires_at'])
        assert is_valid is False
        assert 'invalide' in reason.lower()

    def test_verify_lien_expire(self):
        from affiliations.services import verify_signed_url, generate_signed_url
        result = generate_signed_url('TRACK123', 42, 'http://localhost:8000/')
        past_exp = int(time.time()) - 1
        is_valid, reason = verify_signed_url('TRACK123', 42, result['signature'], past_exp)
        assert is_valid is False
        assert 'expiré' in reason.lower()

    def test_verify_mauvais_product_id(self):
        """La signature doit être invalide si le product_id est falsifié."""
        from affiliations.services import generate_signed_url, verify_signed_url
        result = generate_signed_url('TRACK123', 42, 'http://localhost:8000/')
        is_valid, reason = verify_signed_url('TRACK123', 99, result['signature'], result['expires_at'])
        assert is_valid is False

    def test_cookie_payload(self):
        from affiliations.services import build_session_cookie_payload
        payload = build_session_cookie_payload('TRACK123', int(time.time()) + 3600)
        assert payload['cookie_name'] == 'agc_ref'
        assert payload['tracking_code'] == 'TRACK123'
        assert payload['cookie_httponly'] is False  # Le front JS doit pouvoir le lire


# ── Service auto_validate ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAutoValidateCommissions:
    def test_auto_validation_apres_delai(self, affiliation_link, affilie, vendeur):
        """Les commissions pending > délai doivent être validées automatiquement."""
        from affiliations.models import Commission
        from affiliations.services import auto_validate_pending_commissions
        from orders.models import Order
        from django.utils import timezone
        from datetime import timedelta

        client = User.objects.create_user(username='client_av', password='pass')
        order = Order.objects.create(customer=client, total='50.00')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affilie,
            order_total='50.00', commission_rate='0.15', amount='7.50',
        )
        # Simuler une commission créée il y a 15 jours
        Commission.objects.filter(pk=commission.pk).update(
            created_at=timezone.now() - timedelta(days=15)
        )

        count = auto_validate_pending_commissions(vendeur, delay_days=14)
        assert count == 1
        commission.refresh_from_db()
        assert commission.status == Commission.STATUS_VALIDATED
        assert commission.validated_at is not None

    def test_auto_validation_ne_touche_pas_recentes(self, affiliation_link, affilie, vendeur):
        """Les commissions récentes (< délai) ne doivent pas être validées."""
        from affiliations.models import Commission
        from affiliations.services import auto_validate_pending_commissions
        from orders.models import Order

        client = User.objects.create_user(username='client_nr', password='pass')
        order = Order.objects.create(customer=client, total='50.00')
        Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affilie,
            order_total='50.00', commission_rate='0.15', amount='7.50',
        )
        count = auto_validate_pending_commissions(vendeur, delay_days=14)
        assert count == 0

    def test_auto_validation_ne_touche_pas_paid(self, affiliation_link, affilie, vendeur):
        """Les commissions déjà payées ne doivent pas être modifiées."""
        from affiliations.models import Commission
        from affiliations.services import auto_validate_pending_commissions
        from orders.models import Order
        from django.utils import timezone
        from datetime import timedelta

        client = User.objects.create_user(username='client_paid', password='pass')
        order = Order.objects.create(customer=client, total='50.00')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affilie,
            order_total='50.00', commission_rate='0.15', amount='7.50',
            status=Commission.STATUS_PAID,
        )
        Commission.objects.filter(pk=commission.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        count = auto_validate_pending_commissions(vendeur, delay_days=14)
        assert count == 0


# ── API Affiliations ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAffiliationAPI:
    def test_create_lien(self, auth_affilie, product):
        resp = auth_affilie.post('/api/v1/affiliations/links/', {
            'product': product.pk, 'commission_rate': '0.15',
        })
        assert resp.status_code == 201
        assert 'tracking_code' in resp.data
        assert 'affiliate_url' in resp.data
        assert 'commission_display' in resp.data

    def test_non_affilie_refuse(self, api_client, vendeur, product):
        api_client.force_authenticate(user=vendeur)
        resp = api_client.post('/api/v1/affiliations/links/', {
            'product': product.pk, 'commission_rate': '0.10',
        })
        assert resp.status_code == 403

    def test_signed_url(self, auth_affilie, affiliation_link):
        resp = auth_affilie.post(f'/api/v1/affiliations/links/{affiliation_link.pk}/signed-url/')
        assert resp.status_code == 200
        assert 'url' in resp.data
        assert 'sig=' in resp.data['url']
        assert 'exp=' in resp.data['url']

    def test_validate_url_valide(self, api_client, affiliation_link):
        from affiliations.services import generate_signed_url
        result = generate_signed_url(
            affiliation_link.tracking_code,
            affiliation_link.product_id,
            'http://testserver/',
        )
        resp = api_client.get(
            f'/api/v1/affiliations/validate/'
            f'?ref={affiliation_link.tracking_code}'
            f'&sig={result["signature"]}'
            f'&exp={result["expires_at"]}'
            f'&product_id={affiliation_link.product_id}'
        )
        assert resp.status_code == 200
        assert resp.data['valid'] is True
        assert 'cookie' in resp.data
        assert resp.data['cookie']['cookie_name'] == 'agc_ref'

    def test_validate_url_signature_invalide(self, api_client, affiliation_link):
        import time as t
        resp = api_client.get(
            f'/api/v1/affiliations/validate/'
            f'?ref={affiliation_link.tracking_code}'
            f'&sig=fausse_signature'
            f'&exp={int(t.time()) + 3600}'
            f'&product_id={affiliation_link.product_id}'
        )
        assert resp.status_code == 400
        assert resp.data['valid'] is False

    def test_validate_incremente_clicks(self, api_client, affiliation_link):
        """Chaque validation doit incrémenter le compteur de clics."""
        from affiliations.services import generate_signed_url
        from affiliations.models import AffiliationLink
        result = generate_signed_url(
            affiliation_link.tracking_code,
            affiliation_link.product_id,
            'http://testserver/',
        )
        clicks_avant = affiliation_link.clicks_count
        api_client.get(
            f'/api/v1/affiliations/validate/'
            f'?ref={affiliation_link.tracking_code}'
            f'&sig={result["signature"]}'
            f'&exp={result["expires_at"]}'
            f'&product_id={affiliation_link.product_id}'
        )
        affiliation_link.refresh_from_db()
        assert affiliation_link.clicks_count == clicks_avant + 1

    def test_stats_affilie(self, auth_affilie, affiliation_link):
        resp = auth_affilie.get('/api/v1/affiliations/links/stats/')
        assert resp.status_code == 200
        assert 'total_links' in resp.data
        assert 'total_earned' in resp.data
        assert 'total_clicks' in resp.data
        assert 'conversion_rate' in resp.data

    def test_liste_commissions(self, auth_affilie):
        resp = auth_affilie.get('/api/v1/affiliations/commissions/')
        assert resp.status_code == 200

    def test_marketplace_liste_produits(self, auth_affilie, product):
        resp = auth_affilie.get('/api/v1/affiliations/marketplace/')
        assert resp.status_code == 200
        assert len(resp.data) >= 1

    def test_marketplace_expose_mon_lien(self, auth_affilie, affiliation_link, product):
        resp = auth_affilie.get('/api/v1/affiliations/marketplace/')
        assert resp.status_code == 200
        produit_data = next((p for p in resp.data if p['id'] == product.pk), None)
        assert produit_data is not None
        assert produit_data['my_link'] is not None
        assert produit_data['my_link']['tracking_code'] == affiliation_link.tracking_code


# ── Protection anti-auto-affiliation ─────────────────────────────────────────

@pytest.mark.django_db
class TestAntiAutoAffiliation:
    def test_vendeur_ne_peut_pas_sauto_affilier(self, api_client, vendeur, product):
        """Un vendeur ne peut pas créer un lien sur son propre produit."""
        from users.models import Role
        vendeur.add_role(Role.AFFILIE)
        api_client.force_authenticate(user=vendeur)
        resp = api_client.post('/api/v1/affiliations/links/', {
            'product': product.pk, 'commission_rate': '0.10',
        })
        assert resp.status_code == 400
        assert 'propre produit' in str(resp.data).lower() or 'auto' in str(resp.data).lower()


# ── Validation taux de commission ─────────────────────────────────────────────

@pytest.mark.django_db
class TestValidationTauxCommission:
    def test_taux_superieur_max_absolu_refuse(self, auth_affilie, product):
        """Un taux > 50% doit être refusé."""
        resp = auth_affilie.post('/api/v1/affiliations/links/', {
            'product': product.pk, 'commission_rate': '0.9999',
        })
        assert resp.status_code == 400

    def test_taux_superieur_max_vendeur_refuse(self, auth_affilie, product_with_max_rate):
        """Un taux > max_commission_rate du vendeur doit être refusé."""
        resp = auth_affilie.post('/api/v1/affiliations/links/', {
            'product': product_with_max_rate.pk, 'commission_rate': '0.3000',  # > 20%
        })
        assert resp.status_code == 400
        assert '20' in str(resp.data) or 'taux' in str(resp.data).lower()

    def test_taux_dans_limite_vendeur_accepte(self, auth_affilie, product_with_max_rate):
        """Un taux <= max_commission_rate du vendeur doit être accepté."""
        resp = auth_affilie.post('/api/v1/affiliations/links/', {
            'product': product_with_max_rate.pk, 'commission_rate': '0.1500',  # 15% <= 20%
        })
        assert resp.status_code == 201

    def test_taux_zero_refuse(self, auth_affilie, product):
        """Un taux de 0 doit être refusé."""
        resp = auth_affilie.post('/api/v1/affiliations/links/', {
            'product': product.pk, 'commission_rate': '0.0000',
        })
        assert resp.status_code == 400


# ── Vues Vendeur Affiliations ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestVendeurAffiliationsAPI:
    def test_vendeur_voit_ses_affilies(self, auth_vendeur, affiliation_link):
        resp = auth_vendeur.get('/api/v1/affiliations/vendeur/affiliates/')
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]['affiliate_username'] == 'affilie'

    def test_vendeur_ne_voit_pas_affilies_autres(self, api_client, affiliation_link):
        """Un vendeur ne doit pas voir les affiliés d'un autre vendeur."""
        from users.models import Role
        autre_vendeur = User.objects.create_user(username='autre_vendeur', password='pass')
        autre_vendeur.add_role(Role.ECOMMERCANT)
        api_client.force_authenticate(user=autre_vendeur)
        resp = api_client.get('/api/v1/affiliations/vendeur/affiliates/')
        assert resp.status_code == 200
        assert len(resp.data) == 0

    def test_vendeur_voit_commissions(self, auth_vendeur, affiliation_link, client_user):
        """Le vendeur doit voir les commissions générées sur ses produits."""
        from affiliations.models import Commission
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='50.00')
        Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affiliation_link.affiliate,
            order_total='50.00', commission_rate='0.15', amount='7.50',
        )
        resp = auth_vendeur.get('/api/v1/affiliations/vendeur/commissions/')
        assert resp.status_code == 200
        # La réponse peut être paginée
        results = resp.data.get('results', resp.data)
        assert len(results) >= 1

    def test_vendeur_valide_commission(self, auth_vendeur, affiliation_link, client_user):
        """Le vendeur peut valider manuellement une commission pending."""
        from affiliations.models import Commission
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='50.00')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affiliation_link.affiliate,
            order_total='50.00', commission_rate='0.15', amount='7.50',
        )
        resp = auth_vendeur.patch(
            f'/api/v1/affiliations/vendeur/commissions/{commission.pk}/validate/',
            {'action': 'validate'}, format='json',
        )
        assert resp.status_code == 200
        commission.refresh_from_db()
        assert commission.status == Commission.STATUS_VALIDATED

    def test_vendeur_annule_commission(self, auth_vendeur, affiliation_link, client_user):
        """Le vendeur peut annuler une commission pending."""
        from affiliations.models import Commission
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='50.00')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affiliation_link.affiliate,
            order_total='50.00', commission_rate='0.15', amount='7.50',
        )
        resp = auth_vendeur.patch(
            f'/api/v1/affiliations/vendeur/commissions/{commission.pk}/validate/',
            {'action': 'cancel'}, format='json',
        )
        assert resp.status_code == 200
        commission.refresh_from_db()
        assert commission.status == Commission.STATUS_CANCELLED

    def test_vendeur_ne_peut_pas_annuler_commission_payee(self, auth_vendeur, affiliation_link, client_user):
        """Une commission déjà versée ne peut pas être annulée."""
        from affiliations.models import Commission
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='50.00')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affiliation_link.affiliate,
            order_total='50.00', commission_rate='0.15', amount='7.50',
            status=Commission.STATUS_PAID,
        )
        resp = auth_vendeur.patch(
            f'/api/v1/affiliations/vendeur/commissions/{commission.pk}/validate/',
            {'action': 'cancel'}, format='json',
        )
        assert resp.status_code == 400

    def test_vendeur_filtre_commissions_par_statut(self, auth_vendeur, affiliation_link, client_user):
        """Le filtre ?status= doit fonctionner."""
        from affiliations.models import Commission
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='50.00')
        Commission.objects.create(
            order=order, affiliation_link=affiliation_link, affiliate=affiliation_link.affiliate,
            order_total='50.00', commission_rate='0.15', amount='7.50',
            status=Commission.STATUS_VALIDATED,
        )
        resp = auth_vendeur.get('/api/v1/affiliations/vendeur/commissions/?status=validated')
        assert resp.status_code == 200
        results = resp.data.get('results', resp.data)
        assert all(c['status'] == 'validated' for c in results)

    def test_non_ecommercant_refuse_vue_vendeur(self, auth_affilie):
        """Un affilié ne doit pas accéder aux vues vendeur."""
        resp = auth_affilie.get('/api/v1/affiliations/vendeur/affiliates/')
        assert resp.status_code == 403
