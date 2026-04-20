# Auteur : Gilles - Projet : AGC Space - Module : Orders - Services
"""
Couche de services pour la création de commandes.
Toute la logique ACID est ici — les views restent minces.

Garanties transactionnelles :
  - Décrément du stock ET création de la commande ET création de la commission
    se font dans une seule transaction.atomic().
  - Si l'une des opérations échoue, TOUT est annulé (rollback complet).
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

logger = logging.getLogger('orders')


def _resolve_affiliation(referral_code: str):
    """
    Résout un referral_code en AffiliationLink actif.
    Retourne None si le code est absent ou invalide (pas d'exception — la vente continue).
    """
    if not referral_code:
        return None
    try:
        from affiliations.models import AffiliationLink
        link = AffiliationLink.objects.select_related('affiliate', 'product').get(
            tracking_code=referral_code,
            is_active=True,
        )
        logger.info("Lien d'affiliation résolu — tracking_code: %s, affilié: %s", referral_code, link.affiliate.username)
        return link
    except Exception:
        logger.warning("Referral code '%s' introuvable ou inactif — vente sans commission", referral_code)
        return None


def _check_stock(product, quantity: int) -> None:
    """
    Vérifie que le stock est suffisant pour les produits physiques.
    Lève une ValidationError si insuffisant.
    """
    if not product.is_digital and product.stock < quantity:
        logger.warning(
            "Stock insuffisant pour '%s' — demandé: %d, disponible: %d",
            product.name, quantity, product.stock,
        )
        raise ValidationError(
            f"Stock insuffisant pour '{product.name}' : {product.stock} disponible(s), {quantity} demandé(s)."
        )


def _decrement_stock(product, quantity: int) -> None:
    """
    Décrémente le stock d'un produit physique.
    Utilise F() expression pour éviter les race conditions (atomic update SQL).
    """
    if not product.is_digital:
        from django.db.models import F
        from products.models import Product
        Product.objects.filter(pk=product.pk).update(stock=F('stock') - quantity)
        logger.info("Stock décrémenté — '%s' : %d -> %d", product.name, product.stock, product.stock - quantity)


def _create_commission(order, affiliation_link) -> 'Commission':
    """
    Crée la commission liée à une commande.
    Appelé DANS la transaction atomique — si ça échoue, la commande est aussi annulée.
    """
    from affiliations.models import Commission
    rate = affiliation_link.commission_rate
    amount = (order.total * rate).quantize(Decimal('0.01'))

    commission = Commission.objects.create(
        order=order,
        affiliation_link=affiliation_link,
        affiliate=affiliation_link.affiliate,
        order_total=order.total,
        commission_rate=rate,
        amount=amount,
        status=Commission.STATUS_PENDING,
    )
    logger.info(
        "Commission créée — order #%s, affilié: '%s', montant: %s€ (taux: %.2f%%)",
        order.pk, affiliation_link.affiliate.username, amount, float(rate) * 100,
    )
    return commission


@transaction.atomic
def create_order_atomic(customer, items: list, referral_code: str = '', stripe_payment_intent_id: str = None) -> dict:
    """
    Crée une commande de manière atomique.

    Opérations dans la transaction :
      1. Vérification du stock pour chaque item
      2. Création de l'Order
      3. Création des OrderItems (prix figés)
      4. Calcul du total
      5. Décrément du stock (produits physiques)
      6. Résolution du referral_code → AffiliationLink
      7. Création de la Commission (si affiliation valide)

    Si une étape échoue → rollback complet.
    Retourne : { 'order': Order, 'commission': Commission | None }
    """
    from orders.models import Order, OrderItem

    logger.info(
        "Début transaction atomique — client: '%s', %d item(s), referral: '%s'",
        customer.username, len(items), referral_code or 'aucun',
    )

    try:
        # ── Étape 1 : Vérification stock ──────────────────────────────────────
        for item_data in items:
            _check_stock(item_data['product'], item_data['quantity'])

        # ── Étape 2 : Création Order ──────────────────────────────────────────
        affiliation_link = _resolve_affiliation(referral_code)
        order = Order.objects.create(
            customer=customer,
            referral_code=referral_code or None,
            total=Decimal('0.00'),
            status=Order.STATUS_PENDING,
            stripe_payment_intent_id=stripe_payment_intent_id or None,
        )

        # ── Étape 3 & 4 : OrderItems + calcul total ───────────────────────────
        total = Decimal('0.00')
        for item_data in items:
            product = item_data['product']
            quantity = item_data['quantity']
            unit_price = Decimal(str(product.price))
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
            )
            total += unit_price * quantity

        order.total = total
        order.save(update_fields=['total'])

        # ── Étape 5 : Décrément stock ─────────────────────────────────────────
        for item_data in items:
            _decrement_stock(item_data['product'], item_data['quantity'])

        # ── Étape 6 & 7 : Commission ──────────────────────────────────────────
        commission = None
        if affiliation_link:
            commission = _create_commission(order, affiliation_link)

        logger.info(
            "Transaction atomique réussie — commande #%s, total: %s€, commission: %s",
            order.pk, total, f"{commission.amount}€" if commission else "aucune",
        )
        return {'order': order, 'commission': commission}

    except Exception as e:
        # Le décorateur @transaction.atomic gère le rollback automatiquement
        logger.error(
            "Échec transaction atomique — client: '%s', erreur: %s",
            customer.username, str(e),
        )
        raise


