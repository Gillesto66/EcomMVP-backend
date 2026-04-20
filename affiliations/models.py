# Auteur : Gilles - Projet : AGC Space - Module : Affiliations
import logging
import secrets
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

logger = logging.getLogger('affiliations')

# Taux de commission maximum absolu (protection globale)
MAX_COMMISSION_RATE = Decimal('0.5000')  # 50% max absolu


def generate_tracking_code():
    """Génère un code de tracking unique et sécurisé (URL-safe, 22 chars)."""
    return secrets.token_urlsafe(16)


class AffiliationLink(models.Model):
    """
    Lien d'affiliation entre un affilié et un produit.
    - tracking_code : indexé pour requêtes rapides
    - hmac_signature : dernière signature générée (cache, non autoritaire — la vérité est recalculée)
    - clicks_count : nombre de clics sur le lien (tracking)
    """

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='affiliation_links',
        verbose_name='Produit',
    )
    affiliate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='affiliation_links',
        verbose_name='Affilié',
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        verbose_name='Taux de commission',
        help_text='Ex: 0.1500 = 15%. Limité par le taux max défini par le vendeur.',
        validators=[
            MinValueValidator(Decimal('0.0001')),
            MaxValueValidator(MAX_COMMISSION_RATE),
        ],
    )
    tracking_code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_tracking_code,
        verbose_name='Code de tracking',
    )
    hmac_signature = models.CharField(
        max_length=128,
        blank=True,
        verbose_name='Dernière signature HMAC',
        help_text='Cache de la dernière signature générée — recalculée à chaque appel /signed-url/',
    )
    clicks_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Nombre de clics',
        help_text='Incrémenté à chaque validation de lien (GET /affiliations/validate/)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lien d'affiliation"
        verbose_name_plural = "Liens d'affiliation"
        unique_together = ('product', 'affiliate')

    def __str__(self):
        return f"{self.affiliate.username} → {self.product.name} ({self.tracking_code})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        try:
            super().save(*args, **kwargs)
            action = 'créé' if is_new else 'mis à jour'
            logger.info(
                "AffiliationLink %s — affilié: '%s', produit: '%s', taux: %.2f%%",
                action, self.affiliate.username, self.product.name,
                float(self.commission_rate) * 100,
            )
        except Exception as e:
            logger.error("Erreur sauvegarde AffiliationLink : %s", str(e))
            raise


class Commission(models.Model):
    """
    Commission générée automatiquement lors d'une vente via lien d'affiliation.
    Créée dans la même transaction atomique que la commande (ACID garanti).

    Statuts :
      pending   → calculée, en attente de validation
      validated → validée par l'e-commerçant (délai de rétractation passé)
      paid      → versée à l'affilié
      cancelled → annulée (remboursement, fraude)
    """

    STATUS_PENDING = 'pending'
    STATUS_VALIDATED = 'validated'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'En attente'),
        (STATUS_VALIDATED, 'Validée'),
        (STATUS_PAID, 'Versée'),
        (STATUS_CANCELLED, 'Annulée'),
    ]

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='commission',
        verbose_name='Commande',
    )
    affiliation_link = models.ForeignKey(
        AffiliationLink,
        on_delete=models.PROTECT,
        related_name='commissions',
        verbose_name="Lien d'affiliation",
    )
    affiliate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='commissions_earned',
        verbose_name='Affilié',
    )
    order_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Total de la commande',
        help_text='Figé au moment du calcul',
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        verbose_name='Taux appliqué',
        help_text='Figé au moment du calcul — indépendant des modifications futures du lien',
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Montant de la commission',
        help_text='order_total × commission_rate, calculé automatiquement',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='Statut',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Commission'
        verbose_name_plural = 'Commissions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Commission #{self.pk} — {self.affiliate.username} — {self.amount}€ ({self.status})"

    validated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Date de validation',
        help_text='Renseigné automatiquement lors du passage en statut validated',
    )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        try:
            # Horodatage automatique de la validation
            if self.status == self.STATUS_VALIDATED and not self.validated_at:
                from django.utils import timezone
                self.validated_at = timezone.now()
            super().save(*args, **kwargs)
            action = 'créée' if is_new else 'mise à jour'
            logger.info(
                "Commission #%s %s — affilié: '%s', montant: %s€, statut: %s",
                self.pk, action, self.affiliate.username, self.amount, self.status,
            )
        except Exception as e:
            logger.error("Erreur sauvegarde Commission : %s", str(e))
            raise
