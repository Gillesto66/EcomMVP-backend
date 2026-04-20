# Auteur : Gilles - Projet : AGC Space - Module : Products
import logging
import hashlib
import json
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

logger = logging.getLogger('products')


class Product(models.Model):
    """Produit vendu sur la plateforme AGC Space."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name='Propriétaire',
    )
    name = models.CharField(max_length=255, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Description')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Prix')
    sku = models.CharField(max_length=100, unique=True, db_index=True, verbose_name='SKU')
    is_digital = models.BooleanField(default=False, verbose_name='Produit numérique')
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    stock = models.PositiveIntegerField(
        default=0,
        verbose_name='Stock',
        help_text='Utilisé par les règles de visibilité conditionnelle des blocs',
    )
    views_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Nombre de vues',
        help_text='Incrémenté à chaque appel GET /render/<id>/',
    )
    category = models.CharField(
        max_length=100, blank=True, verbose_name='Catégorie',
        help_text='Ex: Technologie, SaaS, Formation, Physique',
    )
    image_main = models.ImageField(
        upload_to='products/images/', blank=True, null=True,
        verbose_name='Image principale',
        help_text='Image principale affichée sur la page de vente et dans le catalogue',
    )
    image_secondary_1 = models.ImageField(
        upload_to='products/images/', blank=True, null=True,
        verbose_name='Image secondaire 1',
    )
    image_secondary_2 = models.ImageField(
        upload_to='products/images/', blank=True, null=True,
        verbose_name='Image secondaire 2',
    )
    max_commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Taux de commission maximum',
        help_text=(
            'Taux max autorisé pour les affiliés. Ex: 0.3000 = 30%. '
            'Si null, le plafond global (50%) s\'applique.'
        ),
        validators=[
            MinValueValidator(Decimal('0.0001')),
            MaxValueValidator(Decimal('0.5000')),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Produit'
        verbose_name_plural = 'Produits'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        try:
            super().save(*args, **kwargs)
            action = 'créé' if is_new else 'mis à jour'
            logger.info("Produit '%s' (SKU: %s) %s avec succès", self.name, self.sku, action)
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde du produit '%s' : %s", self.name, str(e))
            raise


class Theme(models.Model):
    """
    Design System lié à un e-commerçant.
    Stocke les variables CSS (couleurs, polices, espacements).
    Injecté dans GET /render/ pour que le front applique les variables aux composants React.

    Exemple de variables :
    {
        "primary_color": "#FF6B35",
        "secondary_color": "#2C3E50",
        "font_family": "Inter, sans-serif",
        "font_size_base": "16px",
        "border_radius": "8px",
        "spacing_unit": "8px"
    }
    """
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='theme',
        verbose_name='Propriétaire',
    )
    name = models.CharField(max_length=100, default='Mon thème', verbose_name='Nom du thème')
    variables = models.JSONField(
        default=dict,
        verbose_name='Variables CSS',
        help_text='Dict de variables CSS : {"primary_color": "#FF6B35", "font_family": "Inter"}',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Thème'
        verbose_name_plural = 'Thèmes'

    def __str__(self):
        return f"Thème de {self.owner.username}"

    def save(self, *args, **kwargs):
        try:
            super().save(*args, **kwargs)
            logger.info("Thème mis à jour pour '%s'", self.owner.username)
        except Exception as e:
            logger.error("Erreur sauvegarde thème pour '%s' : %s", self.owner.username, str(e))
            raise

    def to_css_variables(self) -> str:
        """
        Génère un bloc CSS :root avec les variables du thème.
        Utilisé par le Critical CSS Injection.
        """
        if not self.variables:
            return ':root {}'
        lines = ['  '.join([f'--{k.replace("_", "-")}: {v};' for k, v in self.variables.items()])]
        css = ':root {\n  ' + '\n  '.join(
            f'--{k.replace("_", "-")}: {v};' for k, v in self.variables.items()
        ) + '\n}'
        logger.debug("CSS variables générées pour '%s' : %d variables", self.owner.username, len(self.variables))
        return css


class PageTemplate(models.Model):
    """
    Template de page de vente réutilisable — Smart Builder Phase 2.

    Structure JSON complète :
    {
        "blocks": [
            {
                "type": "hero",
                "image": "/media/hero.jpg",
                "text": "Titre principal",
                "visibility": {"stock_min": 1},
                "tracking": {"event": "view_hero"}
            },
            {
                "type": "social_proof",
                "mode": "sales_count",
                "visibility": {}
            },
            {
                "type": "countdown",
                "duration_hours": 24,
                "visibility": {}
            },
            {
                "type": "stock_status",
                "visibility": {"stock_min": 1}
            },
            {
                "type": "buy_button",
                "label": "Acheter maintenant",
                "style": "primary",
                "affiliate_aware": true,
                "visibility": {"stock_min": 1},
                "action": "display_alert",
                "tracking": {"event": "click_buy"}
            }
        ]
    }
    """
    name = models.CharField(max_length=255, verbose_name='Nom du template')
    config = models.JSONField(default=dict, verbose_name='Configuration JSON')
    critical_css = models.TextField(
        blank=True,
        verbose_name='Critical CSS',
        help_text='Blob CSS généré automatiquement à la sauvegarde du template. Élimine le calcul au rendu.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='templates',
        verbose_name='Créé par',
    )
    products = models.ManyToManyField(
        Product,
        through='ProductTemplate',
        blank=True,
        related_name='templates',
        verbose_name='Produits associés',
    )
    is_public = models.BooleanField(
        default=False,
        verbose_name='Partageable',
        help_text='Si True, ce template est visible par tous les e-commerçants',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Template de page'
        verbose_name_plural = 'Templates de page'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def generate_critical_css(self, theme: 'Theme' = None) -> str:
        """
        Génère le Critical CSS à partir du thème + des types de blocs présents.
        Appelé automatiquement au save() pour éliminer le calcul au rendu.
        """
        blocks = self.config.get('blocks', [])
        block_types = {b.get('type') for b in blocks}

        css_parts = []

        # Variables du thème
        if theme:
            css_parts.append(theme.to_css_variables())
        else:
            css_parts.append(':root { --primary-color: #FF6B35; --font-family: Inter, sans-serif; }')

        # CSS critique par type de bloc présent (lazy — on ne génère que ce qui est utilisé)
        if 'hero' in block_types:
            css_parts.append('.block-hero { width: 100%; min-height: 400px; display: flex; align-items: center; }')
        if 'buy_button' in block_types:
            css_parts.append('.block-buy-button { background: var(--primary-color); color: #fff; padding: 16px 32px; border-radius: var(--border-radius, 8px); cursor: pointer; }')
        if 'countdown' in block_types:
            css_parts.append('.block-countdown { font-size: 2rem; font-weight: bold; text-align: center; }')
        if 'social_proof' in block_types:
            css_parts.append('.block-social-proof { background: #f9f9f9; padding: 16px; border-left: 4px solid var(--primary-color); }')
        if 'stock_status' in block_types:
            css_parts.append('.block-stock-status { color: #e74c3c; font-weight: bold; }')
        if 'features' in block_types:
            css_parts.append('.block-features { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }')
        if 'testimonials' in block_types:
            css_parts.append('.block-testimonials { display: flex; flex-wrap: wrap; gap: 16px; }')

        result = '\n'.join(css_parts)
        logger.debug(
            "Critical CSS généré pour template '%s' — %d blocs, %d chars",
            self.name, len(blocks), len(result)
        )
        return result

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        try:
            # Récupérer le thème du créateur pour le Critical CSS
            theme = None
            if self.created_by_id:
                theme = Theme.objects.filter(owner_id=self.created_by_id).first()
            self.critical_css = self.generate_critical_css(theme)
            super().save(*args, **kwargs)
            action = 'créé' if is_new else 'mis à jour'
            logger.info(
                "PageTemplate '%s' %s (public=%s, critical_css=%d chars)",
                self.name, action, self.is_public, len(self.critical_css)
            )
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde du template '%s' : %s", self.name, str(e))
            raise


class ProductTemplate(models.Model):
    """Table de liaison Product <-> PageTemplate avec flag d'activation."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='product_templates',
    )
    template = models.ForeignKey(
        PageTemplate,
        on_delete=models.CASCADE,
        related_name='product_templates',
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Template actif',
        help_text='Un seul template actif par produit recommandé',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Association Produit-Template'
        verbose_name_plural = 'Associations Produit-Template'
        unique_together = ('product', 'template')

    def __str__(self):
        return f"{self.product.name} → {self.template.name}"

    def save(self, *args, **kwargs):
        try:
            super().save(*args, **kwargs)
            logger.info(
                "Template '%s' associé au produit '%s' (actif=%s)",
                self.template.name, self.product.name, self.is_active
            )
        except Exception as e:
            logger.error("Erreur association ProductTemplate : %s", str(e))
            raise
