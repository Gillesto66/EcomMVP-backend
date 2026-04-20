# Auteur : Gilles - Projet : AGC Space - Module : Orders - Tests (Phase 3 + 5/5)
import pytest
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
def client_user(db):
    from users.models import Role
    user = User.objects.create_user(username='client', password='pass')
    user.add_role(Role.CLIENT)
    return user


@pytest.fixture
def affilie(db):
    from users.models import Role
    user = User.objects.create_user(username='affilie', password='pass')
    user.add_role(Role.AFFILIE)
    return user


@pytest.fixture
def auth_client(api_client, client_user):
    api_client.force_authenticate(user=client_user)
    return api_client


@pytest.fixture
def auth_vendeur(api_client, vendeur):
    # Client séparé pour éviter les conflits d'authentification
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=vendeur)
    return client


@pytest.fixture
def product(vendeur):
    from products.models import Product
    return Product.objects.create(
        owner=vendeur, name='Produit Test', price='29.99',
        sku='ORD-TEST-001', stock=10,
    )


@pytest.fixture
def product_physique(vendeur):
    from products.models import Product
    return Product.objects.create(
        owner=vendeur, name='Produit Physique', price='49.99',
        sku='PHYS-001', is_digital=False, stock=5,
    )


@pytest.fixture
def affiliation_link(product, affilie):
    from affiliations.models import AffiliationLink
    return AffiliationLink.objects.create(
        product=product, affiliate=affilie, commission_rate='0.1500'
    )


# ── Modèles ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestOrderModel:
    def test_creation_commande(self, client_user):
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='0.00')
        assert order.status == Order.STATUS_PENDING

    def test_order_number_genere_automatiquement(self, client_user):
        """Le numéro de commande doit être généré automatiquement au format ORD-YYYY-XXXXXX."""
        from orders.models import Order
        import re
        order = Order.objects.create(customer=client_user, total='0.00')
        assert order.order_number != ''
        assert re.match(r'^ORD-\d{4}-\d{6}$', order.order_number), (
            f"Format invalide : {order.order_number}"
        )

    def test_order_numbers_uniques(self, client_user):
        """Deux commandes ne doivent pas avoir le même numéro."""
        from orders.models import Order
        o1 = Order.objects.create(customer=client_user, total='10.00')
        o2 = Order.objects.create(customer=client_user, total='20.00')
        assert o1.order_number != o2.order_number

    def test_unit_price_fige(self, client_user, product):
        from orders.models import Order, OrderItem
        order = Order.objects.create(customer=client_user, total='29.99')
        item = OrderItem.objects.create(order=order, product=product, quantity=1, unit_price='29.99')
        product.price = '99.99'
        product.save()
        item.refresh_from_db()
        assert str(item.unit_price) == '29.99'

    def test_subtotal(self, client_user, product):
        from orders.models import Order, OrderItem
        order = Order.objects.create(customer=client_user, total='59.98')
        item = OrderItem.objects.create(order=order, product=product, quantity=2, unit_price='29.99')
        assert item.subtotal == Decimal('59.98')

    def test_str_order(self, client_user):
        from orders.models import Order
        order = Order.objects.create(customer=client_user, total='0.00')
        assert 'client' in str(order)
        assert 'pending' in str(order)


# ── Service Atomique ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCreateOrderAtomic:
    """
    Tests d'intégration du cœur ACID de la Phase 3.
    Simule le flow complet : vente → stock → commission.
    """

    def test_commande_simple_sans_affiliation(self, client_user, product):
        from orders.services import create_order_atomic
        result = create_order_atomic(
            customer=client_user,
            items=[{'product': product, 'quantity': 2}],
        )
        order = result['order']
        assert order.pk is not None
        assert order.total == Decimal('59.98')
        assert result['commission'] is None

    def test_commande_avec_affiliation_cree_commission(self, client_user, product, affiliation_link):
        """
        Scénario clé Phase 3 :
        Client achète via lien affilié → Commission créée atomiquement.
        """
        from orders.services import create_order_atomic
        result = create_order_atomic(
            customer=client_user,
            items=[{'product': product, 'quantity': 1}],
            referral_code=affiliation_link.tracking_code,
        )
        order = result['order']
        commission = result['commission']

        assert order.referral_code == affiliation_link.tracking_code
        assert commission is not None
        assert commission.affiliate == affiliation_link.affiliate
        assert commission.amount == Decimal('4.50')  # 29.99 * 0.15 = 4.4985 → 4.50
        assert commission.status == 'pending'
        assert commission.order == order

    def test_commission_taux_fige(self, client_user, product, affiliation_link):
        """Le taux de commission doit être figé au moment de la vente."""
        from orders.services import create_order_atomic
        result = create_order_atomic(
            customer=client_user,
            items=[{'product': product, 'quantity': 1}],
            referral_code=affiliation_link.tracking_code,
        )
        commission = result['commission']
        affiliation_link.commission_rate = '0.50'
        affiliation_link.save()
        commission.refresh_from_db()
        assert commission.commission_rate == Decimal('0.1500')

    def test_stock_decremente_produit_physique(self, client_user, product_physique):
        """Le stock doit être décrémenté pour les produits physiques."""
        from orders.services import create_order_atomic
        stock_avant = product_physique.stock
        create_order_atomic(
            customer=client_user,
            items=[{'product': product_physique, 'quantity': 2}],
        )
        product_physique.refresh_from_db()
        assert product_physique.stock == stock_avant - 2

    def test_stock_insuffisant_rollback(self, client_user, product_physique):
        """Si le stock est insuffisant, toute la transaction doit être annulée."""
        from orders.services import create_order_atomic
        from django.core.exceptions import ValidationError
        from orders.models import Order
        orders_avant = Order.objects.count()
        with pytest.raises((ValidationError, Exception)):
            create_order_atomic(
                customer=client_user,
                items=[{'product': product_physique, 'quantity': 999}],
            )
        assert Order.objects.count() == orders_avant

    def test_referral_code_invalide_vente_continue(self, client_user, product):
        """Un referral_code invalide ne doit pas bloquer la vente — juste pas de commission."""
        from orders.services import create_order_atomic
        result = create_order_atomic(
            customer=client_user,
            items=[{'product': product, 'quantity': 1}],
            referral_code='CODE_INEXISTANT',
        )
        assert result['order'].pk is not None
        assert result['commission'] is None

    def test_produit_digital_stock_non_decremente(self, client_user, vendeur):
        """Le stock des produits digitaux ne doit pas être décrémenté."""
        from products.models import Product
        from orders.services import create_order_atomic
        digital = Product.objects.create(
            owner=vendeur, name='Produit Digital', price='29.99',
            sku='DIG-001', stock=10, is_digital=True,
        )
        stock_avant = digital.stock
        create_order_atomic(
            customer=client_user,
            items=[{'product': digital, 'quantity': 5}],
        )
        digital.refresh_from_db()
        assert digital.stock == stock_avant

    def test_commande_avec_stripe_payment_intent(self, client_user, product):
        """Le stripe_payment_intent_id doit être sauvegardé sur la commande."""
        from orders.services import create_order_atomic
        result = create_order_atomic(
            customer=client_user,
            items=[{'product': product, 'quantity': 1}],
            stripe_payment_intent_id='pi_test_123456',
        )
        assert result['order'].stripe_payment_intent_id == 'pi_test_123456'

    def test_order_number_present_apres_creation(self, client_user, product):
        """Le numéro de commande doit être présent après création atomique."""
        from orders.services import create_order_atomic
        import re
        result = create_order_atomic(
            customer=client_user,
            items=[{'product': product, 'quantity': 1}],
        )
        assert re.match(r'^ORD-\d{4}-\d{6}$', result['order'].order_number)


# ── API Orders ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCreateOrderAPI:
    def test_create_order_simple(self, auth_client, product):
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        assert resp.status_code == 201
        assert str(resp.data['total']) == '29.99'
        assert resp.data['commission'] is None

    def test_create_order_retourne_order_number(self, auth_client, product):
        """La réponse doit inclure le numéro de commande lisible."""
        import re
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        assert resp.status_code == 201
        assert 'order_number' in resp.data
        assert re.match(r'^ORD-\d{4}-\d{6}$', resp.data['order_number'])

    def test_create_order_avec_referral(self, auth_client, product, affiliation_link):
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}],
            'referral_code': affiliation_link.tracking_code,
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['commission'] is not None
        assert resp.data['commission']['affiliate'] == 'affilie'
        assert resp.data['commission']['status'] == 'pending'

    def test_commission_montant_correct(self, auth_client, product, affiliation_link):
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}],
            'referral_code': affiliation_link.tracking_code,
        }, format='json')
        # 29.99 * 15% = 4.4985 → arrondi à 4.50
        assert Decimal(resp.data['commission']['amount']) == Decimal('4.50')

    def test_create_order_produit_inexistant(self, auth_client):
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': 9999, 'quantity': 1}]
        }, format='json')
        assert resp.status_code == 400

    def test_list_orders(self, auth_client, product):
        auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        resp = auth_client.get('/api/v1/orders/')
        assert resp.status_code == 200
        results = resp.data.get('results', resp.data)
        assert len(results) == 1

    def test_order_commission_endpoint(self, auth_client, product, affiliation_link):
        create_resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}],
            'referral_code': affiliation_link.tracking_code,
        }, format='json')
        order_id = create_resp.data['id']
        resp = auth_client.get(f'/api/v1/orders/{order_id}/commission/')
        assert resp.status_code == 200
        assert 'amount' in resp.data

    def test_create_order_quantite_invalide(self, auth_client, product):
        """Une quantité de 0 ou négative doit être refusée."""
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 0}]
        }, format='json')
        assert resp.status_code == 400

    def test_create_order_sans_items_refuse(self, auth_client):
        resp = auth_client.post('/api/v1/orders/create/', {
            'items': []
        }, format='json')
        assert resp.status_code == 400


# ── Vue Vendeur Orders ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVendeurOrdersAPI:
    def test_vendeur_voit_ses_commandes(self, auth_vendeur, auth_client, product):
        """Le vendeur doit voir les commandes contenant ses produits."""
        auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        resp = auth_vendeur.get('/api/v1/orders/vendeur/')
        assert resp.status_code == 200
        results = resp.data.get('results', resp.data)
        assert len(results) == 1

    def test_vendeur_ne_voit_pas_commandes_autres(self, api_client, auth_client, product):
        """Un vendeur ne doit pas voir les commandes d'un autre vendeur."""
        from users.models import Role
        autre_vendeur = User.objects.create_user(username='autre_v', password='pass')
        autre_vendeur.add_role(Role.ECOMMERCANT)
        auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        api_client.force_authenticate(user=autre_vendeur)
        resp = api_client.get('/api/v1/orders/vendeur/')
        assert resp.status_code == 200
        results = resp.data.get('results', resp.data)
        assert len(results) == 0

    def test_vendeur_filtre_par_statut(self, auth_vendeur, auth_client, product):
        """Le filtre ?status= doit fonctionner pour le vendeur."""
        auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        resp = auth_vendeur.get('/api/v1/orders/vendeur/?status=pending')
        assert resp.status_code == 200
        results = resp.data.get('results', resp.data)
        assert all(o['status'] == 'pending' for o in results)

    def test_non_ecommercant_refuse(self, api_client, affilie):
        """Un affilié ne doit pas accéder à la vue vendeur."""
        api_client.force_authenticate(user=affilie)
        resp = api_client.get('/api/v1/orders/vendeur/')
        assert resp.status_code == 403

    def test_vendeur_voit_order_number(self, auth_vendeur, auth_client, product):
        """La vue vendeur doit exposer le numéro de commande."""
        import re
        auth_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}]
        }, format='json')
        resp = auth_vendeur.get('/api/v1/orders/vendeur/')
        assert resp.status_code == 200
        results = resp.data.get('results', resp.data)
        assert len(results) == 1
        assert re.match(r'^ORD-\d{4}-\d{6}$', results[0]['order_number'])


# ── Webhook Stripe ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStripeWebhook:
    """
    Tests du webhook Stripe.
    En mode test (sans STRIPE_WEBHOOK_SECRET), le payload est accepté directement.
    """

    def _create_order_with_pi(self, client_user, product, pi_id='pi_test_001'):
        from orders.models import Order, OrderItem
        order = Order.objects.create(
            customer=client_user, total='29.99',
            stripe_payment_intent_id=pi_id,
        )
        OrderItem.objects.create(order=order, product=product, quantity=1, unit_price='29.99')
        return order

    def test_payment_succeeded_passe_commande_en_paid(self, api_client, client_user, product):
        """payment_intent.succeeded doit passer la commande en 'paid'."""
        import json
        order = self._create_order_with_pi(client_user, product, 'pi_test_001')
        payload = json.dumps({
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_test_001'}},
        })
        resp = api_client.post(
            '/api/v1/orders/stripe/webhook/',
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        order.refresh_from_db()
        assert order.status == 'paid'
        assert order.paid_at is not None

    def test_payment_succeeded_valide_commission(self, api_client, client_user, product, affiliation_link):
        """payment_intent.succeeded doit valider la commission associée."""
        import json
        from affiliations.models import Commission
        from orders.models import Order, OrderItem
        order = Order.objects.create(
            customer=client_user, total='29.99',
            stripe_payment_intent_id='pi_test_002',
        )
        OrderItem.objects.create(order=order, product=product, quantity=1, unit_price='29.99')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link,
            affiliate=affiliation_link.affiliate,
            order_total='29.99', commission_rate='0.15', amount='4.50',
        )
        payload = json.dumps({
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_test_002'}},
        })
        api_client.post(
            '/api/v1/orders/stripe/webhook/',
            data=payload,
            content_type='application/json',
        )
        commission.refresh_from_db()
        assert commission.status == 'validated'

    def test_charge_refunded_passe_commande_en_refunded(self, api_client, client_user, product):
        """charge.refunded doit passer la commande en 'refunded'."""
        import json
        order = self._create_order_with_pi(client_user, product, 'pi_test_003')
        payload = json.dumps({
            'type': 'charge.refunded',
            'data': {'object': {'payment_intent': 'pi_test_003'}},
        })
        resp = api_client.post(
            '/api/v1/orders/stripe/webhook/',
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200
        order.refresh_from_db()
        assert order.status == 'refunded'
        assert order.refunded_at is not None

    def test_charge_refunded_annule_commission(self, api_client, client_user, product, affiliation_link):
        """charge.refunded doit annuler la commission associée."""
        import json
        from affiliations.models import Commission
        from orders.models import Order, OrderItem
        order = Order.objects.create(
            customer=client_user, total='29.99',
            stripe_payment_intent_id='pi_test_004',
        )
        OrderItem.objects.create(order=order, product=product, quantity=1, unit_price='29.99')
        commission = Commission.objects.create(
            order=order, affiliation_link=affiliation_link,
            affiliate=affiliation_link.affiliate,
            order_total='29.99', commission_rate='0.15', amount='4.50',
        )
        payload = json.dumps({
            'type': 'charge.refunded',
            'data': {'object': {'payment_intent': 'pi_test_004'}},
        })
        api_client.post(
            '/api/v1/orders/stripe/webhook/',
            data=payload,
            content_type='application/json',
        )
        commission.refresh_from_db()
        assert commission.status == 'cancelled'

    def test_webhook_pi_inconnu_retourne_200(self, api_client):
        """Un webhook avec un PI inconnu doit retourner 200 (idempotence)."""
        import json
        payload = json.dumps({
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_inconnu_999'}},
        })
        resp = api_client.post(
            '/api/v1/orders/stripe/webhook/',
            data=payload,
            content_type='application/json',
        )
        assert resp.status_code == 200

    def test_payment_succeeded_idempotent(self, api_client, client_user, product):
        """Appeler le webhook deux fois ne doit pas changer le statut une deuxième fois."""
        import json
        order = self._create_order_with_pi(client_user, product, 'pi_test_005')
        payload = json.dumps({
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_test_005'}},
        })
        api_client.post('/api/v1/orders/stripe/webhook/', data=payload, content_type='application/json')
        api_client.post('/api/v1/orders/stripe/webhook/', data=payload, content_type='application/json')
        order.refresh_from_db()
        assert order.status == 'paid'


# ── Test d'intégration complet — Simulation vente affiliée ───────────────────

@pytest.mark.django_db
class TestFlowCompletAffiliation:
    """
    Simulation du flow complet Phase 3 :
    1. Affilié génère un lien signé
    2. Front valide la signature → cookie
    3. Client achète avec le referral_code
    4. Commission créée atomiquement
    5. Vérification de l'intégrité des données
    """

    def test_flow_complet(self, api_client, product, affiliation_link, client_user):
        from affiliations.services import generate_signed_url

        # ── Étape 1 : Génération URL signée ──────────────────────────────────
        signed = generate_signed_url(
            affiliation_link.tracking_code,
            affiliation_link.product_id,
            'http://testserver/',
        )
        assert 'sig=' in signed['url']

        # ── Étape 2 : Validation signature ───────────────────────────────────
        resp = api_client.get(
            f'/api/v1/affiliations/validate/'
            f'?ref={affiliation_link.tracking_code}'
            f'&sig={signed["signature"]}'
            f'&exp={signed["expires_at"]}'
            f'&product_id={affiliation_link.product_id}'
        )
        assert resp.status_code == 200
        assert resp.data['valid'] is True
        tracking_code = resp.data['tracking_code']

        # ── Étape 3 : Achat avec referral_code ───────────────────────────────
        api_client.force_authenticate(user=client_user)
        order_resp = api_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}],
            'referral_code': tracking_code,
        }, format='json')
        assert order_resp.status_code == 201

        # ── Étape 4 : Vérification Commission ────────────────────────────────
        commission_data = order_resp.data['commission']
        assert commission_data is not None
        assert commission_data['affiliate'] == affiliation_link.affiliate.username
        assert commission_data['status'] == 'pending'

        # ── Étape 5 : Intégrité des données ──────────────────────────────────
        from affiliations.models import Commission
        commission = Commission.objects.get(pk=commission_data['id'])
        assert commission.order.customer == client_user
        assert commission.order_total == Decimal('29.99')
        assert commission.commission_rate == Decimal('0.1500')
        assert commission.amount == Decimal('4.50')

    def test_flow_complet_avec_stripe_webhook(self, api_client, product, affiliation_link, client_user):
        """
        Flow complet incluant le webhook Stripe :
        Achat → Commission pending → Webhook payment_intent.succeeded → Commission validated
        """
        import json
        from affiliations.models import Commission

        # Achat avec PI Stripe
        api_client.force_authenticate(user=client_user)
        order_resp = api_client.post('/api/v1/orders/create/', {
            'items': [{'product_id': product.pk, 'quantity': 1}],
            'referral_code': affiliation_link.tracking_code,
            'stripe_payment_intent_id': 'pi_flow_001',
        }, format='json')
        assert order_resp.status_code == 201
        assert order_resp.data['commission']['status'] == 'pending'

        # Webhook Stripe
        api_client.logout()
        payload = json.dumps({
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_flow_001'}},
        })
        webhook_resp = api_client.post(
            '/api/v1/orders/stripe/webhook/',
            data=payload,
            content_type='application/json',
        )
        assert webhook_resp.status_code == 200

        # Vérification finale
        commission = Commission.objects.get(pk=order_resp.data['commission']['id'])
        assert commission.status == 'validated'
        assert commission.order.status == 'paid'
