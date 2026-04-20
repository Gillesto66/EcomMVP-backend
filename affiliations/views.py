# Auteur : Gilles - Projet : AGC Space - Module : Affiliations
import logging
from django.db.models import F
from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from affiliations.models import AffiliationLink, Commission
from affiliations.serializers import (
    AffiliationLinkSerializer,
    SignedUrlSerializer,
    ValidateRefSerializer,
    CommissionSerializer,
    VendeurCommissionSerializer,
)
from affiliations.services import (
    generate_signed_url,
    verify_signed_url,
    build_session_cookie_payload,
    auto_validate_pending_commissions,
)
from users.models import Role

logger = logging.getLogger('affiliations')


class IsAffiliate(permissions.BasePermission):
    """Autorise uniquement les utilisateurs avec le rôle 'affilié'."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role(Role.AFFILIE)


class IsEcommercant(permissions.BasePermission):
    """Autorise uniquement les e-commerçants."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.has_role(Role.ECOMMERCANT)


class AffiliationLinkViewSet(viewsets.ModelViewSet):
    """
    CRUD sur les liens d'affiliation.
    Un affilié ne voit et ne gère que ses propres liens.
    """
    serializer_class = AffiliationLinkSerializer
    permission_classes = [permissions.IsAuthenticated, IsAffiliate]

    def get_queryset(self):
        qs = AffiliationLink.objects.filter(
            affiliate=self.request.user
        ).select_related('product', 'affiliate')
        logger.debug(
            "Liens d'affiliation pour '%s' — %d lien(s)",
            self.request.user.username, qs.count(),
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(affiliate=self.request.user)

    @action(detail=True, methods=['post'], url_path='signed-url')
    def signed_url(self, request, pk=None):
        """
        POST /api/v1/affiliations/links/<id>/signed-url/
        Génère une URL signée HMAC pour ce lien d'affiliation.
        L'affilié partage cette URL — elle expire après 30 jours.
        """
        link = self.get_object()
        request_base = request.build_absolute_uri(f'/shop/{link.product_id}/')
        result = generate_signed_url(link.tracking_code, link.product_id, request_base)

        # Mise en cache de la dernière signature
        link.hmac_signature = result['signature']
        link.save(update_fields=['hmac_signature'])

        logger.info(
            "URL signée générée pour '%s' — produit #%s",
            request.user.username, link.product_id,
        )
        return Response(SignedUrlSerializer(result).data)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """
        GET /api/v1/affiliations/links/stats/
        Statistiques globales enrichies pour le dashboard affilié.
        """
        from orders.models import Order
        links = AffiliationLink.objects.filter(affiliate=request.user)
        commissions = Commission.objects.filter(affiliate=request.user)

        total_earned = sum(c.amount for c in commissions.filter(status=Commission.STATUS_PAID))
        pending = sum(c.amount for c in commissions.filter(status=Commission.STATUS_PENDING))
        validated = sum(c.amount for c in commissions.filter(status=Commission.STATUS_VALIDATED))

        # Clics totaux sur tous les liens
        total_clicks = sum(l.clicks_count for l in links)

        # Commandes générées via affiliation
        total_orders_via_affiliation = Order.objects.filter(
            referral_code__in=links.values_list('tracking_code', flat=True)
        ).count()

        # Produits disponibles pour affiliation (publics et actifs)
        from products.models import Product
        available_products = Product.objects.filter(is_active=True).count()

        # Taux de conversion : commandes / clics
        conversion_rate = round(
            (total_orders_via_affiliation / max(total_clicks, 1)) * 100, 1
        ) if total_clicks > 0 else 0.0

        data = {
            'total_links': links.count(),
            'active_links': links.filter(is_active=True).count(),
            'total_commissions': commissions.count(),
            'total_earned': str(total_earned),
            'pending_amount': str(pending),
            'validated_amount': str(validated),
            'total_clicks': total_clicks,
            'total_orders_generated': total_orders_via_affiliation,
            'available_products_count': available_products,
            'conversion_rate': conversion_rate,
        }
        logger.info("Stats affilié '%s' : %s", request.user.username, data)
        return Response(data)


class ValidateAffiliationView(generics.GenericAPIView):
    """
    GET /api/v1/affiliations/validate/?ref=<code>&sig=<hmac>&exp=<ts>&product_id=<id>

    Valide la signature HMAC d'un lien d'affiliation.
    Appelé par le front après le clic sur un lien affilié.
    Si valide, retourne le payload du cookie de session à poser côté client.
    Incrémente le compteur de clics du lien (tracking).

    Flow :
      Clic → GET /validate/ → { valid: true, cookie: {...} } → front pose le cookie
      → client achète → POST /orders/create/ { referral_code } → Commission créée
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ValidateRefSerializer
    throttle_scope = 'validate'  # 30 req/min par IP — anti-spam validation

    def get(self, request):
        ref = request.query_params.get('ref', '')
        sig = request.query_params.get('sig', '')
        product_id = request.query_params.get('product_id', 0)
        try:
            exp = int(request.query_params.get('exp', 0))
            product_id = int(product_id)
        except (ValueError, TypeError):
            return Response({'valid': False, 'reason': 'Paramètres invalides.'}, status=status.HTTP_400_BAD_REQUEST)

        if not all([ref, sig, exp, product_id]):
            return Response({'valid': False, 'reason': 'Paramètres manquants.'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, reason = verify_signed_url(ref, product_id, sig, exp)

        if not is_valid:
            logger.warning("Validation HMAC échouée — ref: %s, raison: %s", ref, reason)
            return Response({'valid': False, 'reason': reason}, status=status.HTTP_400_BAD_REQUEST)

        # Vérifier que le lien existe et est actif
        try:
            link = AffiliationLink.objects.select_related('affiliate', 'product').get(
                tracking_code=ref, is_active=True
            )
        except AffiliationLink.DoesNotExist:
            logger.warning("Lien d'affiliation introuvable pour ref: %s", ref)
            return Response({'valid': False, 'reason': 'Lien introuvable ou inactif.'}, status=status.HTTP_404_NOT_FOUND)

        # ── Tracking des clics (atomic, sans race condition) ──────────────────
        AffiliationLink.objects.filter(pk=link.pk).update(clicks_count=F('clicks_count') + 1)
        logger.info(
            "Clic enregistré — ref: %s, affilié: '%s', produit: '%s'",
            ref, link.affiliate.username, link.product.name,
        )

        cookie_payload = build_session_cookie_payload(ref, exp)
        logger.info(
            "Validation HMAC réussie — ref: %s, affilié: '%s', produit: '%s'",
            ref, link.affiliate.username, link.product.name,
        )
        return Response({
            'valid': True,
            'tracking_code': ref,
            'affiliate': link.affiliate.username,
            'product_id': link.product_id,
            'commission_rate': str(link.commission_rate),
            'cookie': cookie_payload,
        })


class CommissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/v1/affiliations/commissions/
    Liste les commissions de l'affilié connecté.
    Lecture seule — les commissions sont créées automatiquement par le système.
    """
    serializer_class = CommissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAffiliate]

    def get_queryset(self):
        qs = Commission.objects.filter(
            affiliate=self.request.user
        ).select_related('order', 'affiliation_link__product', 'affiliate')
        logger.debug(
            "Commissions pour '%s' — %d commission(s)",
            self.request.user.username, qs.count(),
        )
        return qs


class AffiliationMarketplaceView(generics.ListAPIView):
    """
    GET /api/v1/affiliations/marketplace/
    Liste les produits disponibles pour affiliation (publics, actifs).
    Accessible à tous les affiliés.
    """
    permission_classes = [permissions.IsAuthenticated, IsAffiliate]

    def get(self, request):
        from products.models import Product
        from products.serializers import ProductSerializer
        products = Product.objects.filter(is_active=True).select_related('owner').order_by('-created_at')

        # Enrichir avec le lien d'affiliation existant si présent
        result = []
        for product in products:
            existing_link = AffiliationLink.objects.filter(
                product=product, affiliate=request.user
            ).first()
            product_data = ProductSerializer(product, context={'request': request}).data
            product_data['my_link'] = {
                'tracking_code': existing_link.tracking_code,
                'commission_rate': str(existing_link.commission_rate),
                'commission_display': f"{float(existing_link.commission_rate) * 100:.1f}%",
                'is_active': existing_link.is_active,
                'clicks_count': existing_link.clicks_count,
            } if existing_link else None
            # Exposer le taux max défini par le vendeur
            product_data['max_commission_rate'] = (
                str(product.max_commission_rate) if hasattr(product, 'max_commission_rate') and product.max_commission_rate else None
            )
            result.append(product_data)

        logger.info(
            "Marketplace affilié '%s' — %d produits disponibles",
            request.user.username, len(result)
        )
        return Response(result)


# ── Vues Vendeur ──────────────────────────────────────────────────────────────

class VendeurAffiliatesView(generics.ListAPIView):
    """
    GET /api/v1/affiliations/vendeur/affiliates/
    Le vendeur voit tous ses affiliés (liens actifs sur ses produits).
    """
    permission_classes = [permissions.IsAuthenticated, IsEcommercant]

    def get(self, request):
        links = AffiliationLink.objects.filter(
            product__owner=request.user
        ).select_related('affiliate', 'product').order_by('-created_at')

        result = []
        for link in links:
            commissions = Commission.objects.filter(affiliation_link=link)
            result.append({
                'link_id': link.pk,
                'affiliate_username': link.affiliate.username,
                'product_name': link.product.name,
                'product_id': link.product_id,
                'commission_rate': str(link.commission_rate),
                'commission_display': f"{float(link.commission_rate) * 100:.1f}%",
                'is_active': link.is_active,
                'clicks_count': link.clicks_count,
                'total_commissions': commissions.count(),
                'total_earned': str(sum(c.amount for c in commissions.filter(status=Commission.STATUS_PAID))),
                'pending_amount': str(sum(c.amount for c in commissions.filter(status=Commission.STATUS_PENDING))),
                'created_at': link.created_at,
            })

        logger.info(
            "Vendeur '%s' — %d affilié(s) actifs",
            request.user.username, len(result)
        )
        return Response(result)


class VendeurCommissionsView(generics.ListAPIView):
    """
    GET /api/v1/affiliations/vendeur/commissions/
    Le vendeur voit toutes les commissions générées sur ses produits.
    Peut filtrer par statut : ?status=pending|validated|paid|cancelled
    """
    serializer_class = VendeurCommissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsEcommercant]

    def get_queryset(self):
        qs = Commission.objects.filter(
            affiliation_link__product__owner=self.request.user
        ).select_related('order', 'affiliation_link__product', 'affiliate').order_by('-created_at')

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
            logger.debug(
                "Filtre commissions vendeur '%s' par statut: %s",
                self.request.user.username, status_filter,
            )
        return qs

    def list(self, request, *args, **kwargs):
        # Déclencher la validation automatique des commissions éligibles
        auto_validated = auto_validate_pending_commissions(request.user)
        if auto_validated > 0:
            logger.info(
                "Auto-validation : %d commission(s) validée(s) pour vendeur '%s'",
                auto_validated, request.user.username,
            )
        response = super().list(request, *args, **kwargs)
        response.data['auto_validated_count'] = auto_validated
        return response


class VendeurValidateCommissionView(generics.UpdateAPIView):
    """
    PATCH /api/v1/affiliations/vendeur/commissions/<id>/validate/
    Le vendeur valide manuellement une commission pending.
    """
    permission_classes = [permissions.IsAuthenticated, IsEcommercant]

    def patch(self, request, pk=None):
        try:
            commission = Commission.objects.select_related(
                'affiliation_link__product__owner'
            ).get(pk=pk, affiliation_link__product__owner=request.user)
        except Commission.DoesNotExist:
            logger.warning(
                "Commission #%s introuvable pour vendeur '%s'", pk, request.user.username
            )
            return Response({'detail': 'Commission introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        action_req = request.data.get('action')  # 'validate' ou 'cancel'

        if action_req == 'validate':
            if commission.status != Commission.STATUS_PENDING:
                return Response(
                    {'detail': f"Impossible de valider une commission en statut '{commission.status}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            commission.status = Commission.STATUS_VALIDATED
            commission.save(update_fields=['status', 'updated_at', 'validated_at'])
            logger.info(
                "Commission #%s validée manuellement par vendeur '%s'",
                commission.pk, request.user.username,
            )
            return Response({'detail': 'Commission validée.', 'status': commission.status})

        elif action_req == 'cancel':
            if commission.status == Commission.STATUS_PAID:
                return Response(
                    {'detail': 'Impossible d\'annuler une commission déjà versée.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            commission.status = Commission.STATUS_CANCELLED
            commission.save(update_fields=['status', 'updated_at'])
            logger.info(
                "Commission #%s annulée par vendeur '%s'",
                commission.pk, request.user.username,
            )
            return Response({'detail': 'Commission annulée.', 'status': commission.status})

        return Response(
            {'detail': "Action invalide. Utilisez 'validate' ou 'cancel'."},
            status=status.HTTP_400_BAD_REQUEST,
        )
