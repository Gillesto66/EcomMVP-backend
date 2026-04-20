# Auteur : Gilles - Projet : AGC Space - Module : Products
import logging
import uuid
from rest_framework import serializers
from products.models import Product, PageTemplate, ProductTemplate, Theme
from products.services import validate_block_structure, VALID_BLOCK_TYPES

logger = logging.getLogger('products')


class ProductSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    image_main_url = serializers.SerializerMethodField()
    image_secondary_1_url = serializers.SerializerMethodField()
    image_secondary_2_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'owner', 'owner_username', 'name', 'description',
            'price', 'sku', 'is_digital', 'is_active', 'stock',
            'views_count', 'category',
            'image_main', 'image_main_url',
            'image_secondary_1', 'image_secondary_1_url',
            'image_secondary_2', 'image_secondary_2_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'views_count', 'created_at', 'updated_at']
        extra_kwargs = {
            'sku': {'required': False},
            'image_main': {'required': False, 'write_only': True},
            'image_secondary_1': {'required': False, 'write_only': True},
            'image_secondary_2': {'required': False, 'write_only': True},
        }

    def get_image_main_url(self, obj) -> str | None:
        if obj.image_main:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.image_main.url) if request else obj.image_main.url
        return None

    def get_image_secondary_1_url(self, obj) -> str | None:
        if obj.image_secondary_1:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.image_secondary_1.url) if request else obj.image_secondary_1.url
        return None

    def get_image_secondary_2_url(self, obj) -> str | None:
        if obj.image_secondary_2:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.image_secondary_2.url) if request else obj.image_secondary_2.url
        return None

    def validate_sku(self, value):
        """SKU optionnel — auto-généré si absent."""
        return value or None  # Sera géré dans create()

    def validate_price(self, value):
        """Le prix doit être positif."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Le prix doit être supérieur à 0.")
        return value

    def validate_stock(self, value):
        """Le stock ne peut pas être négatif."""
        if value is not None and value < 0:
            raise serializers.ValidationError("Le stock ne peut pas être négatif.")
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['owner'] = request.user
        # Auto-génération du SKU si absent
        if not validated_data.get('sku'):
            validated_data['sku'] = f"AGC-{uuid.uuid4().hex[:8].upper()}"
            logger.info("SKU auto-généré : %s", validated_data['sku'])
        try:
            product = super().create(validated_data)
            logger.info(
                "Produit '%s' (SKU: %s) créé via API par '%s'",
                product.name, product.sku, request.user.username
            )
            return product
        except Exception as e:
            logger.error("Erreur création produit via API : %s", str(e))
            raise


class ThemeSerializer(serializers.ModelSerializer):
    """
    Sérialise le Design System d'un e-commerçant.
    Variables attendues : primary_color, secondary_color, font_family,
                          font_size_base, border_radius, spacing_unit
    """
    css_preview = serializers.SerializerMethodField()

    class Meta:
        model = Theme
        fields = ['id', 'name', 'variables', 'css_preview', 'updated_at']
        read_only_fields = ['id', 'updated_at']

    def get_css_preview(self, obj) -> str:
        return obj.to_css_variables()

    def validate_variables(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Les variables doivent être un objet JSON.")
        allowed_keys = {
            'primary_color', 'secondary_color', 'background_color',
            'text_color', 'font_family', 'font_size_base',
            'border_radius', 'spacing_unit', 'button_color',
        }
        unknown = set(value.keys()) - allowed_keys
        if unknown:
            raise serializers.ValidationError(
                f"Variables inconnues : {unknown}. Autorisées : {allowed_keys}"
            )
        logger.debug("Variables de thème validées : %d variable(s)", len(value))
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['owner'] = request.user
        theme, created = Theme.objects.update_or_create(
            owner=request.user,
            defaults=validated_data,
        )
        action = 'créé' if created else 'mis à jour'
        logger.info("Thème %s pour '%s'", action, request.user.username)
        return theme


class PageTemplateSerializer(serializers.ModelSerializer):
    """
    Smart Builder — Phase 2.
    Valide la structure JSON complète incluant les règles de visibilité
    et les types de blocs conversion-ready.
    """
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    product_count = serializers.IntegerField(source='products.count', read_only=True)
    critical_css = serializers.CharField(read_only=True)

    class Meta:
        model = PageTemplate
        fields = [
            'id', 'name', 'config', 'critical_css', 'created_by',
            'created_by_username', 'is_public', 'product_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'critical_css', 'created_at', 'updated_at']

    def validate_config(self, value):
        if not isinstance(value, dict):
            logger.error('Config validation failed: not a dict, received %s', type(value))
            raise serializers.ValidationError("La config doit être un objet JSON.")
        if 'blocks' not in value:
            logger.error('Config validation failed: no blocks key, keys present: %s', list(value.keys()))
            raise serializers.ValidationError("La config doit contenir une clé 'blocks'.")
        if not isinstance(value['blocks'], list):
            logger.error('Config validation failed: blocks is not a list, received %s', type(value['blocks']))
            raise serializers.ValidationError("'blocks' doit être une liste.")

        # Validation de chaque bloc
        all_errors = []
        for i, block in enumerate(value['blocks']):
            block_errors = validate_block_structure(block)
            for err in block_errors:
                all_errors.append(f"Bloc #{i} : {err}")

        if all_errors:
            logger.error('Config validation failed with block errors: %s', all_errors)
            raise serializers.ValidationError(all_errors)

        logger.debug("Config PageTemplate validée — %d bloc(s)", len(value['blocks']))
        return value

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user
        try:
            template = super().create(validated_data)
            logger.info(
                "PageTemplate '%s' créé par '%s' (critical_css: %d chars)",
                template.name, request.user.username, len(template.critical_css)
            )
            return template
        except Exception as e:
            logger.error("Erreur création PageTemplate : %s", str(e))
            raise


class ProductTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTemplate
        fields = ['id', 'product', 'template', 'is_active', 'assigned_at']
        read_only_fields = ['id', 'assigned_at']

    def validate(self, data):
        product = data.get('product')
        request = self.context.get('request')
        if product and product.owner != request.user:
            logger.warning(
                "Tentative d'assignation non autorisée par '%s'", request.user.username
            )
            raise serializers.ValidationError("Vous n'êtes pas propriétaire de ce produit.")
        return data


class PageRenderSerializer(serializers.Serializer):
    """
    Payload complet retourné par GET /render/<product_id>/.
    Contient : produit, thème, blocs enrichis, critical CSS.
    Le front React n'a qu'à consommer ce payload pour construire la page.
    """
    product = ProductSerializer(read_only=True)
    theme = ThemeSerializer(read_only=True)
    template = serializers.DictField(read_only=True)
    blocks = serializers.ListField(read_only=True)
    critical_css = serializers.CharField(read_only=True)
    meta = serializers.DictField(read_only=True)
