# Auteur : Gilles - Projet : AGC Space - Module : Orders
import logging
from rest_framework import serializers
from orders.models import Order, OrderItem
from products.models import Product

logger = logging.getLogger('orders')


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'subtotal']
        read_only_fields = ['id', 'unit_price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_username = serializers.CharField(source='customer.username', read_only=True)
    commission = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer', 'customer_username', 'referral_code',
            'status', 'total', 'items', 'commission',
            'stripe_payment_intent_id', 'paid_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'order_number', 'customer', 'total', 'paid_at', 'created_at', 'updated_at']

    def get_commission(self, obj) -> dict | None:
        """Expose les infos de commission si la commande est affiliée."""
        try:
            c = obj.commission
            return {
                'id': c.pk,
                'amount': str(c.amount),
                'rate': str(c.commission_rate),
                'status': c.status,
                'affiliate': c.affiliate.username,
            }
        except Exception:
            return None


class VendeurOrderSerializer(serializers.ModelSerializer):
    """
    Sérialise une commande pour la vue vendeur.
    N'expose que les items appartenant au vendeur connecté.
    """
    items = serializers.SerializerMethodField()
    customer_username = serializers.CharField(source='customer.username', read_only=True)
    commission = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer_username', 'status', 'total',
            'items', 'commission', 'paid_at', 'created_at',
        ]
        read_only_fields = fields

    def get_items(self, obj) -> list:
        """Retourne uniquement les items appartenant au vendeur connecté."""
        request = self.context.get('request')
        if not request:
            return []
        items = obj.items.filter(product__owner=request.user).select_related('product')
        return OrderItemSerializer(items, many=True).data

    def get_commission(self, obj) -> dict | None:
        try:
            c = obj.commission
            return {
                'id': c.pk,
                'amount': str(c.amount),
                'status': c.status,
                'affiliate': c.affiliate.username,
            }
        except Exception:
            return None


class CreateOrderSerializer(serializers.Serializer):
    """
    Sérializer de création de commande Phase 3.
    Délègue toute la logique ACID à orders.services.create_order_atomic().
    """
    referral_code = serializers.CharField(required=False, allow_blank=True, default='')
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
    stripe_payment_intent_id = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_items(self, items):
        validated = []
        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            if not product_id:
                raise serializers.ValidationError("Chaque item doit avoir un 'product_id'.")
            try:
                product = Product.objects.get(pk=product_id, is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError(f"Produit #{product_id} introuvable ou inactif.")
            try:
                quantity = int(quantity)
                if quantity < 1:
                    raise ValueError
            except (ValueError, TypeError):
                raise serializers.ValidationError(f"Quantité invalide pour le produit #{product_id}.")
            validated.append({'product': product, 'quantity': quantity})
        logger.debug("Items validés : %d produit(s)", len(validated))
        return validated

    def create(self, validated_data):
        from orders.services import create_order_atomic
        request = self.context.get('request')
        stripe_pi_id = validated_data.get('stripe_payment_intent_id', '') or None
        try:
            result = create_order_atomic(
                customer=request.user,
                items=validated_data['items'],
                referral_code=validated_data.get('referral_code', ''),
                stripe_payment_intent_id=stripe_pi_id,
            )
            return result['order']
        except Exception as e:
            logger.error("Erreur création commande pour '%s' : %s", request.user.username, str(e))
            raise serializers.ValidationError(str(e))
