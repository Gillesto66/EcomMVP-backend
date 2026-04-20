# Auteur : Gilles - Projet : AGC Space - Module : Settings de test
"""
Settings spécifiques aux tests.
- SQLite en mémoire (pas besoin de PostgreSQL)
- Cache locmem (pas besoin de Redis)
- Désactive les migrations GIN PostgreSQL-only
"""
from agc_core.settings import *  # noqa: F401, F403

# ── Base de données SQLite en mémoire ─────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'CONN_MAX_AGE': 60,  # Simuler les connexions persistantes en test
    }
}

# ── Cache locmem ──────────────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'agcspace-test',
        'OPTIONS': {
            'IGNORE_EXCEPTIONS': True,  # Cohérence avec la config production
        },
    }
}

# ── Désactiver les migrations personnalisées (GIN indexes PostgreSQL-only) ────
# Les migrations RunSQL avec hints={'target_db': 'postgresql'} échouent sur SQLite
# On utilise un MigrationExecutor qui ignore les RunSQL
class DisableMigrations:
    def __contains__(self, item):
        return True
    def __getitem__(self, item):
        return None

# Ne pas désactiver les migrations — on laisse Django créer le schéma normalement
# Les migrations RunSQL avec CONCURRENTLY échoueront sur SQLite
# On les ignore via une migration override

# ── Sécurité allégée pour les tests ──────────────────────────────────────────
SECRET_KEY = 'test-secret-key-not-for-production'
HMAC_SECRET_KEY = 'test-hmac-key-not-for-production'
DEBUG = True

# ── Désactiver les logs verbeux en tests ─────────────────────────────────────
import logging
logging.disable(logging.CRITICAL)
