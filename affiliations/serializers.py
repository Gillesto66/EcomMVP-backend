# Auteur : Gilles - Projet : AGC Space - Module : Affiliations
import logging
from decimal import Decimal
from rest_framework import serializers
from affiliations.models import AffiliationLink, Commission, MAX_COMMISSION_RATE
from users.models import Role

logger = logging.getLogger('affiliations')


class AffiliationLinkSerializer(serializers.ModelSerializer):
    affiliate_username = serializers.CharField(source='affiliate.username', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    affiliate_url = serializers.SerializerMethodField()
    commission_display = serializers.SerializerMethodField()
    clicks_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AffiliationLink
        fields = [
            'id', 'product', 'product_name', 'affiliate', 'affiliate_username',
            'commission_rate', 'commission_display', 'tracking_code',
            'is_active', 'affiliate_url', 'clicks_count', 'created_at',
        ]
        read_only_fields = ['id', 'affiliate', 'tracking_code', 'hmac_signature', 'clicks_count', 'created_at']

    def get_affiliate_url(self, obj) -> str:
        """URL de base sans signature — utiliser /signed-url/ pour l'URL sécurisée."""
        request = self.context.get('request')
        base = request.build_absolute_uri('/') if request else 'http://localhost:8000/'
        return f"{base}shop/{obj.product_id}/?ref={obj.tracking_code}"

    def get_commission_display(self, obj) -> str:
        return f"{float(obj.commission_rate) * 100:.1f}%"

    def validate(self, data):
        request = self.context.get('request')
        user = request.user

        if not user.has_role(Role.AFFILIE):
            logger.warning(
                "Tentative de création de lien sans rôle affilié par '%s'", user.username
            )
            raise serializers.ValidationError(
                "Vous devez avoir le rôle 'affilié' pour créer un lien d'affiliation."
            )

        product = data.get('product') or (self.instance.product if self.instance else None)
        commission_rate = data.get('commission_rate')

        # ── Protection anti-auto-affiliation ─────────────────────────────────
        if product and product.owner == user:
            logger.warning(
                "Tentative d'auto-affiliation par '%s' sur son propre produit '%s'",
                user.username, product.name,
            )
            raise serializers.ValidationError(
                "Vous ne pouvez pas créer un lien d'affiliation sur votre propre produit."
            )

        # ── Validation du taux de commission ─────────────────────────────────
        if commission_rate is not None and product:
            # Taux max absolu
            if commission_rate > MAX_COMMISSION_RATE:
                raise serializers.ValidationError(
                    f"Le taux de commission ne peut pas dépasser {float(MAX_COMMISSION_RATE) * 100:.0f}%."
                )
            # Taux max défini par le vendeur sur ce produit
            max_rate = getattr(product, 'max_commission_rate', None)
            if max_rate is not None and commission_rate > max_rate:
                logger.warning(
                    "Taux %.2f%% refusé pour '%s' — max vendeur: %.2f%%",
                    float(commission_rate) * 100, user.username, float(max_rate) * 100,
                )
                raise serializers.ValidationError(
                    f"Le vendeur a limité le taux de commission à {float(max_rate) * 100:.1f}% pour ce produit."
                )

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['affiliate'] = request.user
        try:
            link = super().create(validated_data)
            logger.info(
                "Lien d'affiliation créé — affilié: '%s', produit: '%s', taux: %.2f%%",
                request.user.username, link.product.name, float(link.commission_rate) * 100,
            )
            return link
        except Exception as e:
            logger.error("Erreur création lien d'affiliation : %s", str(e))
            raise


class SignedUrlSerializer(serializers.Serializer):
    """Payload retourné par POST /affiliations/links/<id>/signed-url/"""
    url = serializers.CharField(read_only=True)
    expires_at = serializers.IntegerField(read_only=True)
    tracking_code = serializers.CharField(read_only=True)
    signature = serializers.CharField(read_only=True)


class ValidateRefSerializer(serializers.Serializer):
    """Payload de validation d'un lien d'affiliation — GET /affiliations/validate/"""
    ref = serializers.CharField()
    sig = serializers.CharField()
    exp = serializers.IntegerField()
    product_id = serializers.IntegerField()


class CommissionSerializer(serializers.ModelSerializer):
    """Sérialise une commission pour l'affilié."""
    affiliate_username = serializers.CharField(source='affiliate.username', read_only=True)
    order_id = serializers.IntegerField(source='order.pk', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    product_name = serializers.SerializerMethodField()
    commission_display = serializers.SerializerMethodField()

    class Meta:
        model = Commission
        fields = [
            'id', 'order_id', 'order_number', 'product_name', 'affiliate_username',
            'order_total', 'commission_rate', 'commission_display',
            'amount', 'status', 'validated_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_product_name(self, obj) -> str:
        try:
            return obj.affiliation_link.product.name
        except Exception:
            return ''

    def get_commission_display(self, obj) -> str:
        return f"{float(obj.commission_rate) * 100:.1f}%"


class VendeurCommissionSerializer(serializers.ModelSerializer):
    """Sérialise une commission pour le vendeur (vue vendeur)."""
    affiliate_username = serializers.CharField(source='affiliate.username', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    product_name = serializers.SerializerMethodField()
    commission_display = serializers.SerializerMethodField()

    class Meta:
        model = Commission
        fields = [
            'id', 'order_number', 'product_name', 'affiliate_username',
            'order_total', 'commission_rate', 'commission_display',
            'amount', 'status', 'validated_at', 'created_at',
        ]
        read_only_fields = fields

    def get_product_name(self, obj) -> str:
        try:
            return obj.affiliation_link.product.name
        except Exception:
            return ''

    def get_commission_display(self, obj) -> str:
        return f"{float(obj.commission_rate) * 100:.1f}%"
