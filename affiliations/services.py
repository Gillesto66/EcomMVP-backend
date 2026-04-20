# Auteur : Gilles - Projet : AGC Space - Module : Affiliations - Services
"""
Couche de services pour la sécurité HMAC et la gestion des sessions d'affiliation.

Flow complet Phase 3 :
  1. Affilié génère un lien signé  → POST /affiliations/links/<id>/signed-url/
  2. Visiteur clique               → GET  /shop/<product_id>/?ref=<code>&sig=<hmac>
  3. Backend valide la signature   → GET  /api/v1/affiliations/validate/?ref=<code>&sig=<hmac>
  4. Front pose un cookie          → { tracking_code, expires }
  5. Client achète                 → POST /api/v1/orders/create/ { referral_code: <code> }
  6. Backend crée Order + Commission dans transaction.atomic
"""
import hmac
import hashlib
import logging
import time
from django.conf import settings

logger = logging.getLogger('affiliations')

# Durée de validité d'un lien signé : 30 jours
LINK_TTL_SECONDS = 30 * 24 * 3600


def _get_hmac_secret() -> bytes:
    """Retourne la clé secrète HMAC depuis les settings."""
    secret = getattr(settings, 'HMAC_SECRET_KEY', settings.SECRET_KEY)
    return secret.encode('utf-8')


def generate_signed_url(tracking_code: str, product_id: int, base_url: str) -> dict:
    """
    Génère une URL d'affiliation signée avec HMAC-SHA256.
    La signature couvre : tracking_code + product_id + timestamp d'expiration.
    Cela empêche toute falsification du taux de commission ou du produit.

    Retourne :
        {
            "url": "http://.../?ref=<code>&sig=<hmac>&exp=<ts>",
            "expires_at": <timestamp>,
            "tracking_code": "<code>"
        }
    """
    expires_at = int(time.time()) + LINK_TTL_SECONDS
    message = f"{tracking_code}:{product_id}:{expires_at}".encode('utf-8')
    signature = hmac.new(_get_hmac_secret(), message, hashlib.sha256).hexdigest()

    url = f"{base_url.rstrip('/')}/?ref={tracking_code}&sig={signature}&exp={expires_at}"
    logger.info(
        "URL signée générée — tracking_code: %s, product_id: %s, expire: %s",
        tracking_code, product_id, expires_at
    )
    return {
        'url': url,
        'expires_at': expires_at,
        'tracking_code': tracking_code,
        'signature': signature,
    }


def verify_signed_url(tracking_code: str, product_id: int, signature: str, expires_at: int) -> tuple[bool, str]:
    """
    Vérifie la signature HMAC d'un lien d'affiliation.

    Retourne : (is_valid: bool, reason: str)
    """
    # 1. Vérification expiration
    now = int(time.time())
    if now > expires_at:
        logger.warning(
            "Lien expiré — tracking_code: %s, expiré depuis %ds",
            tracking_code, now - expires_at
        )
        return False, "Lien d'affiliation expiré."

    # 2. Recalcul de la signature attendue
    message = f"{tracking_code}:{product_id}:{expires_at}".encode('utf-8')
    expected = hmac.new(_get_hmac_secret(), message, hashlib.sha256).hexdigest()

    # 3. Comparaison en temps constant (protection timing attack)
    if not hmac.compare_digest(expected, signature):
        logger.warning(
            "Signature HMAC invalide — tracking_code: %s (tentative de falsification ?)",
            tracking_code
        )
        return False, "Signature invalide."

    logger.info("Signature HMAC validée — tracking_code: %s", tracking_code)
    return True, "OK"


def build_session_cookie_payload(tracking_code: str, expires_at: int) -> dict:
    """
    Construit le payload du cookie de session d'affiliation.
    Le front pose ce cookie après validation de la signature.
    Il sera lu lors de la création de la commande.
    """
    return {
        'tracking_code': tracking_code,
        'expires_at': expires_at,
        'cookie_name': 'agc_ref',
        'cookie_max_age': LINK_TTL_SECONDS,
        'cookie_samesite': 'Lax',
        'cookie_httponly': False,  # Le front JS doit pouvoir le lire
    }


def auto_validate_pending_commissions(vendor_user, delay_days: int = None) -> int:
    """
    Valide automatiquement les commissions en statut 'pending' dont le délai
    de rétractation est dépassé.

    Le délai est configurable via settings.COMMISSION_VALIDATION_DELAY_DAYS (défaut : 14 jours).
    Appelé lors de la consultation des commissions vendeur.

    Retourne le nombre de commissions validées.
    """
    from affiliations.models import Commission
    from django.utils import timezone
    from datetime import timedelta

    if delay_days is None:
        delay_days = getattr(settings, 'COMMISSION_VALIDATION_DELAY_DAYS', 14)

    cutoff = timezone.now() - timedelta(days=delay_days)

    eligible = Commission.objects.filter(
        affiliation_link__product__owner=vendor_user,
        status=Commission.STATUS_PENDING,
        created_at__lte=cutoff,
    )
    count = eligible.count()
    if count > 0:
        eligible.update(
            status=Commission.STATUS_VALIDATED,
            validated_at=timezone.now(),
        )
        logger.info(
            "Auto-validation : %d commission(s) validée(s) pour vendeur '%s' (délai: %d jours)",
            count, vendor_user.username, delay_days,
        )
    return count
