# Auteur : Gilles - Projet : AGC Space - Module : Orders
import logging
from django.db import models
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('orders')


def generate_order_number():
    """
    Génère un numéro de commande lisible : ORD-YYYY-XXXXXX
    Ex: ORD-2026-000042
    """
    year = timezone.now().year
    # On utilise un compteur basé sur le nombre de commandes de l'année
    from django.db.models import Count
    count = Order.objects.filter(created_at__year=year).count() + 1
    return f"ORD-{year}-{count:06d}"


class Order(models.Model):
    """
    Commande client.
    Le champ referral_code permet de tracer l'affiliation à l'origine de la vente.
    Les transactions atomiques (Phase 3) garantissent l'intégrité stock + commission.
    """

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REFUNDED = 'refunded'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'En attente'),
        (STATUS_PAID, 'Payée'),
        (STATUS_CANCELLED, 'Annulée'),
        (STATUS_REFUNDED, 'Remboursée'),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='Client',
    )
    order_number = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        db_index=True,
        verbose_name='Numéro de commande',
        help_text='Généré automatiquement : ORD-YYYY-XXXXXX',
    )
    referral_code = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        verbose_name='Code de parrainage',
        help_text='Code de tracking de l\'affilié à l\'origine de la vente',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='Statut',
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Total',
    )
    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        verbose_name='Stripe PaymentIntent ID',
        help_text='ID du PaymentIntent Stripe — renseigné lors du checkout',
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Date de paiement',
        help_text='Renseigné automatiquement lors du webhook Stripe payment_intent.succeeded',
    )
    refunded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Date de remboursement',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Commande'
        verbose_name_plural = 'Commandes'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number or f'#{self.pk}'} — {self.customer.username} ({self.status})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Génération du numéro de commande à la création
        if is_new and not self.order_number:
            self.order_number = generate_order_number()
        try:
            super().save(*args, **kwargs)
            action = 'créée' if is_new else 'mise à jour'
            logger.info(
                "Commande %s %s — client: '%s', statut: %s, total: %s€",
                self.order_number, action, self.customer.username, self.status, self.total
            )
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde de la commande : %s", str(e))
            raise


class OrderItem(models.Model):
    """
    Ligne de commande.
    unit_price est figé au moment de l'achat pour l'intégrité comptable.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Commande',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name='Produit',
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='Quantité')
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Prix unitaire',
        help_text='Prix figé au moment de l\'achat — ne pas modifier',
    )

    class Meta:
        verbose_name = 'Ligne de commande'
        verbose_name_plural = 'Lignes de commande'

    def __str__(self):
        return f"{self.quantity}x {self.product.name} @ {self.unit_price}€"

    @property
    def subtotal(self):
        from decimal import Decimal
        return Decimal(str(self.unit_price)) * self.quantity

    def save(self, *args, **kwargs):
        try:
            super().save(*args, **kwargs)
            logger.info(
                "OrderItem sauvegardé — produit: '%s', qté: %s, prix: %s€",
                self.product.name, self.quantity, self.unit_price
            )
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde de l'OrderItem : %s", str(e))
            raise
