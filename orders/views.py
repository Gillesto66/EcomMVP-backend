# Auteur : Gilles - Projet : AGC Space - Module : Orders
import logging
from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from orders.models import Order
from orders.serializers import OrderSerializer, CreateOrderSerializer, VendeurOrderSerializer

logger = logging.getLogger('orders')


class IsEcommercant(permissions.BasePermission):
    """Autorise uniquement les e-commerçants."""
    def has_permission(self, request, view):
        from users.models import Role
        return request.user.is_authenticated and request.user.has_role(Role.ECOMMERCANT)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture des commandes de l'utilisateur connecté."""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(
            customer=self.request.user
        ).prefetch_related('items__product').select_related('customer')

    @action(detail=True, methods=['get'], url_path='commission')
    def commission(self, request, pk=None):
        """GET /api/v1/orders/<id>/commission/ — détail de la commission liée."""
        order = self.get_object()
        try:
            from affiliations.serializers import CommissionSerializer
            return Response(CommissionSerializer(order.commission).data)
        except Exception:
            return Response(
                {'detail': 'Aucune commission pour cette commande.'},
                status=status.HTTP_404_NOT_FOUND,
            )


class CreateOrderView(generics.CreateAPIView):
    """
    POST /api/v1/orders/create/
    Crée une commande via transaction atomique (Phase 3).

    Garanties ACID :
      - Stock vérifié et décrémenté dans la même transaction
      - Commission créée atomiquement si referral_code valide
      - Rollback complet si une étape échoue
    """
    serializer_class = CreateOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        logger.info(
            "Commande %s créée — client: '%s', total: %s€, affilié: %s",
            order.order_number, request.user.username, order.total,
            order.referral_code or 'aucun',
        )
        return Response(
            OrderSerializer(order, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class VendeurOrdersView(generics.ListAPIView):
    """
    GET /api/v1/orders/vendeur/
    Le vendeur voit toutes les commandes contenant ses produits.
    Peut filtrer par statut : ?status=pending|paid|cancelled|refunded
    """
    serializer_class = VendeurOrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsEcommercant]

    def get_queryset(self):
        qs = Order.objects.filter(
            items__product__owner=self.request.user
        ).prefetch_related('items__product').select_related('customer').distinct().order_by('-created_at')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
            logger.debug(
                "Filtre commandes vendeur '%s' par statut: %s",
                self.request.user.username, status_filter,
            )
        logger.info(
            "Commandes vendeur '%s' — %d commande(s)",
            self.request.user.username, qs.count(),
        )
        return qs


class StripeWebhookView(generics.GenericAPIView):
    """
    POST /api/v1/orders/stripe/webhook/
    Reçoit les événements Stripe et met à jour le statut des commandes.

    Événements traités :
      - payment_intent.succeeded  → commande paid, commission validated
      - payment_intent.payment_failed → log warning
      - charge.refunded           → commande refunded, commission cancelled

    Sécurité : signature Stripe vérifiée via STRIPE_WEBHOOK_SECRET.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from django.conf import settings
        from django.utils import timezone

        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

        # ── Vérification signature Stripe ─────────────────────────────────────
        if webhook_secret:
            try:
                import stripe
                event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            except Exception as e:
                logger.warning("Webhook Stripe : signature invalide — %s", str(e))
                return Response({'detail': 'Signature invalide.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Mode développement sans secret configuré
            import json
            try:
                event = json.loads(payload)
            except Exception:
                return Response({'detail': 'Payload invalide.'}, status=status.HTTP_400_BAD_REQUEST)
            logger.warning("Webhook Stripe reçu sans vérification de signature (STRIPE_WEBHOOK_SECRET absent)")

        event_type = event.get('type') if isinstance(event, dict) else event['type']
        logger.info("Webhook Stripe reçu — type: %s", event_type)

        # ── payment_intent.succeeded ──────────────────────────────────────────
        if event_type == 'payment_intent.succeeded':
            self._handle_payment_succeeded(event, timezone)

        # ── payment_intent.payment_failed ─────────────────────────────────────
        elif event_type == 'payment_intent.payment_failed':
            pi_id = event['data']['object']['id']
            logger.warning("Paiement échoué — PaymentIntent: %s", pi_id)

        # ── charge.refunded ───────────────────────────────────────────────────
        elif event_type == 'charge.refunded':
            self._handle_refund(event, timezone)

        return Response({'received': True})

    def _handle_payment_succeeded(self, event, timezone):
        """Passe la commande en 'paid' et valide la commission associée."""
        pi = event['data']['object']
        pi_id = pi['id']
        try:
            order = Order.objects.select_related('customer').get(
                stripe_payment_intent_id=pi_id
            )
        except Order.DoesNotExist:
            logger.warning("Webhook payment_intent.succeeded : commande introuvable pour PI %s", pi_id)
            return

        if order.status == Order.STATUS_PAID:
            logger.info("Commande %s déjà payée — webhook ignoré", order.order_number)
            return

        order.status = Order.STATUS_PAID
        order.paid_at = timezone.now()
        order.save(update_fields=['status', 'paid_at', 'updated_at'])
        logger.info(
            "Commande %s passée en 'paid' via webhook Stripe (PI: %s)",
            order.order_number, pi_id,
        )

        # Valider la commission associée si elle existe
        try:
            commission = order.commission
            if commission.status == commission.STATUS_PENDING:
                commission.status = commission.STATUS_VALIDATED
                commission.save(update_fields=['status', 'validated_at', 'updated_at'])
                logger.info(
                    "Commission #%s validée automatiquement après paiement Stripe",
                    commission.pk,
                )
        except Exception:
            pass  # Pas de commission — normal

    def _handle_refund(self, event, timezone):
        """Passe la commande en 'refunded' et annule la commission."""
        charge = event['data']['object']
        pi_id = charge.get('payment_intent')
        if not pi_id:
            return
        try:
            order = Order.objects.get(stripe_payment_intent_id=pi_id)
        except Order.DoesNotExist:
            logger.warning("Webhook charge.refunded : commande introuvable pour PI %s", pi_id)
            return

        order.status = Order.STATUS_REFUNDED
        order.refunded_at = timezone.now()
        order.save(update_fields=['status', 'refunded_at', 'updated_at'])
        logger.info(
            "Commande %s passée en 'refunded' via webhook Stripe",
            order.order_number,
        )

        # Annuler la commission associée
        try:
            commission = order.commission
            if commission.status not in (commission.STATUS_PAID, commission.STATUS_CANCELLED):
                commission.status = commission.STATUS_CANCELLED
                commission.save(update_fields=['status', 'updated_at'])
                logger.info(
                    "Commission #%s annulée suite au remboursement de la commande %s",
                    commission.pk, order.order_number,
                )
        except Exception:
            pass
