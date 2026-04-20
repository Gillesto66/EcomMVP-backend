# Auteur : Gilles - Projet : AGC Space - Module : Products - Services
"""
Couche de services métier pour le Smart Builder.
Isole la logique complexe des views et serializers.
"""
import logging
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('products')

# --- Composants "Conversion-Ready" ---

SMART_COMPONENT_TYPES = {'social_proof', 'countdown', 'stock_status', 'buy_button'}

VALID_BLOCK_TYPES = {
    'hero', 'features', 'testimonials', 'buy_button',
    'social_proof', 'countdown', 'stock_status', 'text', 'image', 'video',
    'image_gallery', 'video_embed', 'faq_accordion', 'cta_banner',
    'testimonials_carousel', 'pricing_table', 'contact_form',
}


def get_social_proof_data(product) -> dict:
    """
    Composant Social Proof — basé sur les logs de vente réels.
    Retourne le nombre de ventes et d'acheteurs récents (30 derniers jours).
    """
    try:
        from orders.models import OrderItem, Order
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_sales = OrderItem.objects.filter(
            product=product,
            order__status='paid',
            order__created_at__gte=thirty_days_ago,
        ).aggregate(
            total_sold=Sum('quantity'),
            buyer_count=Count('order__customer', distinct=True),
        )
        data = {
            'total_sold': recent_sales['total_sold'] or 0,
            'buyer_count': recent_sales['buyer_count'] or 0,
            'period_days': 30,
        }
        logger.debug(
            "Social proof pour '%s' : %d ventes, %d acheteurs (30j)",
            product.name, data['total_sold'], data['buyer_count']
        )
        return data
    except Exception as e:
        logger.error("Erreur calcul social proof pour produit #%s : %s", product.pk, str(e))
        return {'total_sold': 0, 'buyer_count': 0, 'period_days': 30}


def get_countdown_data(product, duration_hours: int = 24) -> dict:
    """
    Composant Countdown Timer — basé sur le created_at du produit.
    Calcule le temps restant avant la fin d'une offre fictive.
    """
    try:
        deadline = product.created_at + timedelta(hours=duration_hours)
        now = timezone.now()
        remaining = deadline - now
        seconds_left = max(int(remaining.total_seconds()), 0)
        data = {
            'deadline_iso': deadline.isoformat(),
            'seconds_remaining': seconds_left,
            'is_expired': seconds_left == 0,
        }
        logger.debug(
            "Countdown pour '%s' : %ds restants (deadline: %s)",
            product.name, seconds_left, deadline.isoformat()
        )
        return data
    except Exception as e:
        logger.error("Erreur calcul countdown pour produit #%s : %s", product.pk, str(e))
        return {'seconds_remaining': 0, 'is_expired': True}


def get_stock_status_data(product) -> dict:
    """
    Composant Stock Status — état du stock en temps réel.
    """
    stock = product.stock
    if stock == 0:
        label, level = 'Rupture de stock', 'out'
    elif stock <= 5:
        label, level = f'Plus que {stock} en stock !', 'low'
    else:
        label, level = 'En stock', 'ok'

    data = {'stock': stock, 'label': label, 'level': level}
    logger.debug("Stock status pour '%s' : %s (%s)", product.name, label, level)
    return data


def evaluate_block_visibility(block: dict, product) -> bool:
    """
    Évalue les règles de visibilité conditionnelle d'un bloc.
    Règles supportées :
      - stock_min : affiche le bloc si stock >= valeur
      - stock_max : affiche le bloc si stock <= valeur
    Le front interprète les règles complexes ; le backend pré-filtre les cas simples.
    """
    visibility = block.get('visibility', {})
    if not visibility:
        return True

    stock_min = visibility.get('stock_min')
    stock_max = visibility.get('stock_max')

    if stock_min is not None and product.stock < stock_min:
        logger.debug(
            "Bloc '%s' masqué — stock %d < stock_min %d",
            block.get('type'), product.stock, stock_min
        )
        return False
    if stock_max is not None and product.stock > stock_max:
        logger.debug(
            "Bloc '%s' masqué — stock %d > stock_max %d",
            block.get('type'), product.stock, stock_max
        )
        return False
    return True


def enrich_blocks(blocks: list, product) -> list:
    """
    Enrichit chaque bloc avec ses données dynamiques et évalue sa visibilité.
    Retourne uniquement les blocs visibles, avec leurs données injectées.
    """
    enriched = []
    for block in blocks:
        block_type = block.get('type')

        # Évaluation visibilité
        if not evaluate_block_visibility(block, product):
            continue

        enriched_block = dict(block)

        # Injection des données dynamiques par type
        if block_type == 'social_proof':
            enriched_block['data'] = get_social_proof_data(product)

        elif block_type == 'countdown':
            duration = block.get('duration_hours', 24)
            enriched_block['data'] = get_countdown_data(product, duration)

        elif block_type == 'stock_status':
            enriched_block['data'] = get_stock_status_data(product)

        elif block_type == 'buy_button':
            # Affiliate Aware : le front détectera le ref_id en URL
            # et modifiera le comportement du bouton (cookie de session)
            enriched_block['affiliate_aware'] = block.get('affiliate_aware', True)
            enriched_block['data'] = get_stock_status_data(product)

        enriched.append(enriched_block)

    logger.info(
        "Blocs enrichis pour produit '%s' : %d/%d blocs visibles",
        product.name, len(enriched), len(blocks)
    )
    return enriched


def validate_block_structure(block: dict) -> list:
    """
    Valide la structure d'un bloc individuel.
    Retourne une liste d'erreurs (vide si valide).
    """
    errors = []
    block_type = block.get('type')

    if not block_type:
        errors.append("Chaque bloc doit avoir un champ 'type'.")
        return errors

    if block_type not in VALID_BLOCK_TYPES:
        errors.append(f"Type de bloc inconnu : '{block_type}'. Types valides : {sorted(VALID_BLOCK_TYPES)}")

    visibility = block.get('visibility', {})
    if not isinstance(visibility, dict):
        errors.append(f"Le champ 'visibility' du bloc '{block_type}' doit être un objet.")

    return errors
