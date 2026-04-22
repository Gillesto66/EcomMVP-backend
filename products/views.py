# Auteur : Gilles - Projet : AGC Space - Module : Products
import logging
from decimal import Decimal
from rest_framework import viewsets, generics, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Sum, F, Q
from products.models import Product, PageTemplate, ProductTemplate, Theme
from products.serializers import (
    ProductSerializer,
    PageTemplateSerializer,
    ProductTemplateSerializer,
    ThemeSerializer,
)
from products.services import enrich_blocks
from products.cache import (
    get_render_cache, set_render_cache,
    get_theme_cache, set_theme_cache,
    invalidate_render_cache, invalidate_theme_cache,
    invalidate_all_renders_for_owner,
)

logger = logging.getLogger('products')


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        owner = getattr(obj, 'owner', getattr(obj, 'created_by', None))
        return owner == request.user


# ── Pagination ────────────────────────────────────────────────────────────────

class ProductPagination(PageNumberPagination):
    """
    Pagination pour la liste des produits.
    Taille par défaut : 20. Max : 100.
    Paramètre : ?page=2&page_size=10
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ── ProductViewSet ────────────────────────────────────────────────────────────

class ProductViewSet(viewsets.ModelViewSet):
    """
    CRUD produits. Seul le propriétaire peut modifier.

    Filtres disponibles :
      ?search=django          → recherche dans name + description
      ?category=Formation     → filtre par catégorie exacte
      ?is_digital=true        → filtre produits numériques
      ?min_price=10&max_price=100 → filtre par fourchette de prix
      ?ordering=price         → tri par prix (- pour décroissant)
      ?ordering=-views_count  → tri par popularité
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    pagination_class = ProductPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'category', 'sku']
    ordering_fields = ['price', 'created_at', 'views_count', 'name']
    ordering = ['-created_at']

    def get_permissions(self):
        """Lecture publique (list/retrieve), écriture authentifiée."""
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]

    def get_queryset(self):
        if self.action in ['list', 'retrieve']:
            # ?mine=true → produits du vendeur connecté (dashboard)
            # sinon → marketplace publique (produits actifs de tous)
            if self.request.query_params.get('mine') == 'true':
                return Product.objects.filter(
                    owner=self.request.user
                ).select_related('owner')
            qs = Product.objects.filter(is_active=True).select_related('owner')
        else:
            qs = Product.objects.filter(owner=self.request.user)

        # Filtres supplémentaires sur la liste publique
        if self.action == 'list':
            category = self.request.query_params.get('category')
            is_digital = self.request.query_params.get('is_digital')
            min_price = self.request.query_params.get('min_price')
            max_price = self.request.query_params.get('max_price')

            if category:
                qs = qs.filter(category__iexact=category)
                logger.debug("Filtre catégorie appliqué : '%s'", category)

            if is_digital is not None:
                qs = qs.filter(is_digital=(is_digital.lower() == 'true'))

            if min_price:
                try:
                    qs = qs.filter(price__gte=Decimal(min_price))
                except Exception:
                    logger.warning("Paramètre min_price invalide : '%s'", min_price)

            if max_price:
                try:
                    qs = qs.filter(price__lte=Decimal(max_price))
                except Exception:
                    logger.warning("Paramètre max_price invalide : '%s'", max_price)

        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        invalidate_render_cache(instance.pk)

    @action(detail=True, methods=['get'], url_path='templates')
    def templates(self, request, pk=None):
        product = self.get_object()
        pts = ProductTemplate.objects.filter(product=product).select_related('template')
        data = [
            {'template_id': pt.template.id, 'template_name': pt.template.name, 'is_active': pt.is_active}
            for pt in pts
        ]
        logger.debug("Templates récupérés pour '%s' : %d", product.name, len(data))
        return Response(data)


# ── ThemeViewSet ──────────────────────────────────────────────────────────────

class ThemeViewSet(viewsets.ModelViewSet):
    """Design System de l'e-commerçant. Un seul thème par utilisateur."""
    serializer_class = ThemeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Theme.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        invalidate_theme_cache(instance.owner_id)
        invalidate_all_renders_for_owner(instance.owner_id)

    @action(detail=False, methods=['get'], url_path='mine')
    def mine(self, request):
        """Récupère ou crée le thème — avec cache Redis."""
        cached = get_theme_cache(request.user.pk)
        if cached:
            return Response(cached)

        theme, created = Theme.objects.get_or_create(
            owner=request.user,
            defaults={'name': 'Mon thème', 'variables': {
                'primary_color': '#FF6B35',
                'secondary_color': '#2C3E50',
                'font_family': 'Inter, sans-serif',
                'border_radius': '8px',
                'spacing_unit': '8px',
            }}
        )
        if created:
            logger.info("Thème par défaut créé pour '%s'", request.user.username)

        data = ThemeSerializer(theme, context={'request': request}).data
        set_theme_cache(request.user.pk, data)
        return Response(data)


# ── PageTemplateViewSet ───────────────────────────────────────────────────────

class PageTemplateViewSet(viewsets.ModelViewSet):
    """CRUD templates. Lecture publique des templates partagés."""
    serializer_class = PageTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if self.action in ['list', 'retrieve']:
            return (
                PageTemplate.objects.filter(created_by=user) |
                PageTemplate.objects.filter(is_public=True)
            ).select_related('created_by').distinct()
        return PageTemplate.objects.filter(created_by=user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        product_ids = list(instance.products.values_list('pk', flat=True))
        for pid in product_ids:
            invalidate_render_cache(pid)
        logger.info(
            "Cache invalidé pour %d produit(s) après mise à jour du template '%s'",
            len(product_ids), instance.name,
        )

    @action(detail=True, methods=['post'], url_path='assign')
    def assign_to_product(self, request, pk=None):
        template = self.get_object()
        product_id = request.data.get('product_id')
        is_active = request.data.get('is_active', False)
        product = get_object_or_404(Product, pk=product_id, owner=request.user)
        pt, created = ProductTemplate.objects.get_or_create(
            product=product, template=template,
            defaults={'is_active': is_active},
        )
        if not created:
            pt.is_active = is_active
            pt.save()
        invalidate_render_cache(product.pk)
        label = 'créée' if created else 'mise à jour'
        logger.info("Association '%s' → '%s' %s (actif=%s)", template.name, product.name, label, is_active)
        return Response(ProductTemplateSerializer(pt, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='css')
    def get_css(self, request, pk=None):
        template = self.get_object()
        return Response({'template_id': template.pk, 'critical_css': template.critical_css})


# ── VendeurStatsView ──────────────────────────────────────────────────────────

class VendeurStatsView(generics.GenericAPIView):
    """
    GET /api/v1/dashboard/stats/
    Statistiques complètes pour le dashboard vendeur.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            from orders.models import Order
            from affiliations.models import AffiliationLink, Commission

            products_qs = Product.objects.filter(owner=user)
            active_products = products_qs.filter(is_active=True)

            paid_orders = Order.objects.filter(
                items__product__owner=user,
                status=Order.STATUS_PAID,
            ).distinct()
            total_revenue = paid_orders.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

            active_affiliates = AffiliationLink.objects.filter(
                product__owner=user, is_active=True
            ).values('affiliate').distinct().count()

            commissions = Commission.objects.filter(affiliation_link__product__owner=user)
            avg_rate_sum = commissions.aggregate(avg=Sum('commission_rate'))['avg']
            count = commissions.count()
            avg_commission_pct = float(avg_rate_sum / count) * 100 if avg_rate_sum and count > 0 else 0.0

            total_affiliate_gain = commissions.filter(
                status__in=['validated', 'paid']
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            top_product = active_products.order_by('-views_count').first()
            products_data = ProductSerializer(
                active_products.order_by('-views_count')[:6],
                many=True, context={'request': request}
            ).data

            data = {
                'total_revenue': str(total_revenue),
                'active_products_count': active_products.count(),
                'active_affiliates_count': active_affiliates,
                'avg_commission_pct': round(avg_commission_pct, 1),
                'total_affiliate_gain': str(total_affiliate_gain),
                'top_product': ProductSerializer(top_product, context={'request': request}).data if top_product else None,
                'products': products_data,
            }
            logger.info(
                "Stats vendeur '%s' — CA: %s€, %d produits, %d affiliés",
                user.username, total_revenue, active_products.count(), active_affiliates
            )
            return Response(data)
        except Exception as e:
            logger.error("Erreur stats vendeur '%s' : %s", user.username, str(e))
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ── BuilderInitView ───────────────────────────────────────────────────────────

class BuilderInitView(generics.GenericAPIView):
    """
    GET /api/v1/builder/<product_id>/init/
    Retourne le payload de rendu pour le builder.
    Crée automatiquement un template par défaut si le produit n'en a pas encore.
    Évite le "Produit introuvable" quand on clique sur Builder pour un nouveau produit.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id, owner=request.user)

        pt = ProductTemplate.objects.filter(
            product=product, is_active=True
        ).select_related('template').first()

        if not pt:
            logger.info(
                "Aucun template pour '%s' — création d'un template par défaut",
                product.name
            )
            default_config = {
                'blocks': [
                    {'type': 'hero', 'text': product.name, 'visibility': {}},
                    {'type': 'features', 'items': [], 'visibility': {}},
                    {'type': 'buy_button', 'label': 'Acheter maintenant',
                     'affiliate_aware': True, 'visibility': {'stock_min': 0}},
                ]
            }
            template = PageTemplate.objects.create(
                name=f'Page de vente — {product.name}',
                config=default_config,
                created_by=request.user,
                is_public=False,
            )
            pt = ProductTemplate.objects.create(
                product=product, template=template, is_active=True,
            )
            logger.info("Template '%s' créé pour le produit '%s'", template.name, product.name)

        template = pt.template
        blocks = template.config.get('blocks', [])
        enriched = enrich_blocks(blocks, product)

        theme_data = get_theme_cache(product.owner_id)
        if theme_data is None:
            theme = Theme.objects.filter(owner=product.owner).first()
            theme_data = ThemeSerializer(theme).data if theme else {}
            if theme_data:
                set_theme_cache(product.owner_id, theme_data)

        payload = {
            'product': ProductSerializer(product, context={'request': request}).data,
            'theme': theme_data,
            'template': {'id': template.pk, 'name': template.name},
            'blocks': enriched,
            'critical_css': template.critical_css,
            'meta': {
                'product_id': product.pk,
                'template_id': template.pk,
                'tracking_events': [],
                'affiliate_aware_blocks': [b.get('type') for b in enriched if b.get('affiliate_aware')],
            },
        }
        logger.info("Builder init — produit '%s', template '%s'", product.name, template.name)
        return Response(payload)


# ── PageRenderView ────────────────────────────────────────────────────────────

class PageRenderView(generics.RetrieveAPIView):
    """
    GET /api/v1/render/<product_id>/
    Endpoint public — payload complet pour le rendu React.
    Résultat mis en cache Redis (TTL: CACHE_TTL_PAGE_RENDER).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        cached = get_render_cache(product_id)
        if cached is not None:
            return Response(cached)

        product = get_object_or_404(
            Product.objects.select_related('owner'),
            pk=product_id, is_active=True,
        )
        Product.objects.filter(pk=product_id).update(views_count=F('views_count') + 1)
        product.refresh_from_db(fields=['views_count'])

        pt = (
            ProductTemplate.objects
            .filter(product=product, is_active=True)
            .select_related('template__created_by')
            .first()
        )

        if not pt:
            logger.warning("Aucun template actif pour le produit #%s", product_id)
            return Response(
                {'detail': 'Aucun template actif pour ce produit.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        template = pt.template
        blocks = template.config.get('blocks', [])
        enriched = enrich_blocks(blocks, product)

        theme_data = get_theme_cache(product.owner_id)
        if theme_data is None:
            theme = Theme.objects.filter(owner=product.owner).first()
            theme_data = ThemeSerializer(theme).data if theme else {}
            if theme_data:
                set_theme_cache(product.owner_id, theme_data)

        meta = {
            'product_id': product.pk,
            'template_id': template.pk,
            'tracking_events': [b.get('tracking') for b in enriched if b.get('tracking')],
            'affiliate_aware_blocks': [b.get('type') for b in enriched if b.get('affiliate_aware')],
        }

        payload = {
            'product': ProductSerializer(product, context={'request': request}).data,
            'theme': theme_data,
            'template': {'id': template.pk, 'name': template.name},
            'blocks': enriched,
            'critical_css': template.critical_css,
            'meta': meta,
        }

        set_render_cache(product_id, payload)
        logger.info(
            "Rendu calculé et mis en cache — produit #%s, template '%s', %d blocs",
            product_id, template.name, len(enriched),
        )
        return Response(payload)


# ── FileUploadView ────────────────────────────────────────────────────────────

# Types MIME autorisés — détection par extension + contenu (Pillow pour les images)
_ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
_ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.ogg'}
_MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5 MB
_MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB


class FileUploadView(generics.CreateAPIView):
    """
    POST /api/v1/upload/
    Upload de fichiers (images et vidéos) pour le builder.

    Sécurité :
      - Validation de l'extension ET du contenu réel (Pillow pour les images)
      - Nom de fichier unique (user_id + uuid) — pas de path traversal possible
      - Taille limitée : 5 MB images, 50 MB vidéos
      - Seuls les utilisateurs authentifiés peuvent uploader
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        import os
        import uuid as uuid_lib
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        # ── Validation extension ──────────────────────────────────────────────
        _, ext = os.path.splitext(uploaded_file.name.lower())
        if ext in _ALLOWED_IMAGE_EXTENSIONS:
            file_type = 'image'
            max_size = _MAX_IMAGE_SIZE
        elif ext in _ALLOWED_VIDEO_EXTENSIONS:
            file_type = 'video'
            max_size = _MAX_VIDEO_SIZE
        else:
            logger.warning(
                "Upload refusé — extension non autorisée '%s' par user #%s",
                ext, request.user.id
            )
            return Response(
                {'error': f"Extension non supportée : {ext}. Images : {_ALLOWED_IMAGE_EXTENSIONS}, Vidéos : {_ALLOWED_VIDEO_EXTENSIONS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Validation taille ─────────────────────────────────────────────────
        if uploaded_file.size > max_size:
            logger.warning(
                "Upload refusé — fichier trop volumineux (%d bytes) par user #%s",
                uploaded_file.size, request.user.id
            )
            return Response(
                {'error': f"Fichier trop volumineux. Max : {max_size // (1024 * 1024)} MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Validation contenu image (Pillow) ─────────────────────────────────
        if file_type == 'image':
            try:
                from PIL import Image
                img = Image.open(uploaded_file)
                img.verify()  # Vérifie que c'est bien une image valide
                uploaded_file.seek(0)
                logger.debug("Image validée par Pillow — format: %s", img.format)
            except Exception as e:
                logger.warning(
                    "Upload refusé — image invalide ou corrompue par user #%s : %s",
                    request.user.id, str(e)
                )
                return Response(
                    {'error': 'Fichier image invalide ou corrompu.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── Nom de fichier sécurisé (uuid — pas de path traversal) ───────────
        unique_name = f"{request.user.id}_{uuid_lib.uuid4().hex}{ext}"
        file_path = f"uploads/{request.user.id}/{file_type}s/{unique_name}"

        # ── Sauvegarde ────────────────────────────────────────────────────────
        try:
            file_content = uploaded_file.read()
            saved_path = default_storage.save(file_path, ContentFile(file_content))
            file_url = default_storage.url(saved_path)
            logger.info(
                "Fichier uploadé — type: %s, taille: %d bytes, url: %s, user: #%s",
                file_type, uploaded_file.size, file_url, request.user.id
            )
            return Response({
                'url': file_url,
                'type': file_type,
                'size': uploaded_file.size,
                'filename': unique_name,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error("Erreur sauvegarde fichier pour user #%s : %s", request.user.id, str(e))
            return Response({'error': 'Erreur lors de la sauvegarde du fichier.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
