# Auteur : Gilles - Projet : AGC Space - Module : Products - Cache
"""
Couche de cache Redis pour les pages de vente et les thèmes.

Stratégie :
  - GET /render/<product_id>/  → cache 5 min (TTL configurable via CACHE_TTL_PAGE_RENDER)
  - GET /themes/mine/          → cache 1h  (TTL configurable via CACHE_TTL_THEME)
  - Invalidation automatique au save() de Product, PageTemplate, Theme

Clés Redis :
  agcspace:render:product:<id>      → payload complet de rendu
  agcspace:theme:<user_id>          → thème CSS d'un e-commerçant
  agcspace:product:<id>             → données produit
"""
import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger('cache')

# ── Clés de cache ─────────────────────────────────────────────────────────────

def _key_render(product_id: int) -> str:
    return f'render:product:{product_id}'

def _key_theme(user_id: int) -> str:
    return f'theme:{user_id}'

def _key_product(product_id: int) -> str:
    return f'product:{product_id}'


# ── Lecture / écriture ────────────────────────────────────────────────────────

def get_render_cache(product_id: int) -> dict | None:
    """Retourne le payload de rendu depuis le cache Redis, ou None si absent."""
    key = _key_render(product_id)
    data = cache.get(key)
    if data is not None:
        logger.debug("Cache HIT — render produit #%s", product_id)
    else:
        logger.debug("Cache MISS — render produit #%s", product_id)
    return data


def set_render_cache(product_id: int, payload: dict) -> None:
    """Met en cache le payload de rendu avec le TTL configuré."""
    key = _key_render(product_id)
    ttl = getattr(settings, 'CACHE_TTL_PAGE_RENDER', 300)
    try:
        cache.set(key, payload, timeout=ttl)
        logger.info("Cache SET — render produit #%s (TTL: %ds)", product_id, ttl)
    except Exception as e:
        # Redis down → on continue sans cache (IGNORE_EXCEPTIONS=True dans settings)
        logger.warning("Cache SET échoué pour produit #%s : %s", product_id, str(e))


def invalidate_render_cache(product_id: int) -> None:
    """Invalide le cache de rendu d'un produit (appelé au save() du produit/template)."""
    key = _key_render(product_id)
    cache.delete(key)
    logger.info("Cache INVALIDÉ — render produit #%s", product_id)


def get_theme_cache(user_id: int) -> dict | None:
    key = _key_theme(user_id)
    data = cache.get(key)
    if data is not None:
        logger.debug("Cache HIT — thème user #%s", user_id)
    return data


def set_theme_cache(user_id: int, payload: dict) -> None:
    key = _key_theme(user_id)
    ttl = getattr(settings, 'CACHE_TTL_THEME', 3600)
    try:
        cache.set(key, payload, timeout=ttl)
        logger.info("Cache SET — thème user #%s (TTL: %ds)", user_id, ttl)
    except Exception as e:
        logger.warning("Cache SET thème échoué pour user #%s : %s", user_id, str(e))


def invalidate_theme_cache(user_id: int) -> None:
    cache.delete(_key_theme(user_id))
    logger.info("Cache INVALIDÉ — thème user #%s", user_id)


def invalidate_all_renders_for_owner(owner_id: int) -> None:
    """
    Invalide tous les caches de rendu des produits d'un e-commerçant.
    Appelé quand le thème change — tous les renders doivent être recalculés.
    """
    try:
        from products.models import Product
        product_ids = Product.objects.filter(owner_id=owner_id).values_list('pk', flat=True)
        for pid in product_ids:
            invalidate_render_cache(pid)
        logger.info(
            "Cache INVALIDÉ — %d render(s) pour owner #%s (changement de thème)",
            len(product_ids), owner_id,
        )
    except Exception as e:
        logger.error("Erreur invalidation cache owner #%s : %s", owner_id, str(e))
