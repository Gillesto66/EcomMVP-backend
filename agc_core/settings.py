# Auteur : Gilles - Projet : AGC Space - Module : Configuration Django
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ── Applications ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',  # Blacklist JWT — révocation des refresh tokens
    'corsheaders',
    # AGC Space apps
    'users',
    'products',
    'affiliations',
    'orders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',          # Compression gzip côté Django (fallback si Nginx absent)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'agc_core.middleware.RequestLoggingMiddleware',    # Logs structurés des requêtes
]

ROOT_URLCONF = 'agc_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'agc_core.wsgi.application'

# ── Base de données PostgreSQL ────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'agc_space'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            # Active les index GIN sur les champs JSONField (JSONB natif PostgreSQL)
            # Permet des requêtes rapides sur products.config et templates.config
            'options': '-c default_text_search_config=pg_catalog.french',
        },
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),  # Connexions persistantes
    }
}

# ── Cache Redis ───────────────────────────────────────────────────────────────
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'IGNORE_EXCEPTIONS': True,  # Si Redis est down, l'app continue sans cache
        },
        'KEY_PREFIX': 'agcspace',
        'TIMEOUT': int(os.getenv('CACHE_TTL', '300')),  # 5 min par défaut
    }
}

# TTL spécifiques par type de données
CACHE_TTL_PAGE_RENDER = int(os.getenv('CACHE_TTL_PAGE_RENDER', '300'))   # 5 min — pages de vente
CACHE_TTL_THEME = int(os.getenv('CACHE_TTL_THEME', '3600'))              # 1h  — thèmes CSS
CACHE_TTL_PRODUCT = int(os.getenv('CACHE_TTL_PRODUCT', '120'))           # 2min — produits

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'users.User'

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('THROTTLE_ANON', '100/hour'),
        'user': os.getenv('THROTTLE_USER', '1000/hour'),
        'login': os.getenv('THROTTLE_LOGIN', '10/minute'),       # Anti brute-force login
        'register': os.getenv('THROTTLE_REGISTER', '5/minute'),  # Anti spam inscription
        'validate': os.getenv('THROTTLE_VALIDATE', '30/minute'), # Validation liens affiliés
    },
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': int(os.getenv('PAGE_SIZE', '20')),
}

# ── JWT ───────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '60'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,  # Révoque l'ancien refresh token après rotation
    'AUTH_HEADER_TYPES': ('Bearer',),
    'UPDATE_LAST_LOGIN': True,  # Met à jour last_login à chaque connexion
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS', 'http://localhost:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# Accepter tous les sous-domaines Ngrok via regex
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://.*\.ngrok-free\.app$',
    r'^https://.*\.ngrok-free\.dev$',
    r'^https://.*\.ngrok\.io$',
]

# ── Sécurité production ───────────────────────────────────────────────────────
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000          # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# ── HMAC ──────────────────────────────────────────────────────────────────────
# Clé dédiée pour les signatures HMAC des liens d'affiliation
# Si absente, fallback sur SECRET_KEY (acceptable, mais une clé dédiée est préférable)
HMAC_SECRET_KEY = os.getenv('HMAC_SECRET_KEY', SECRET_KEY)

# ── Monitoring Sentry ─────────────────────────────────────────────────────────
SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style='url'),
            RedisIntegration(),
        ],
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
        send_default_pii=False,  # RGPD — pas de données personnelles dans Sentry
        environment=os.getenv('SENTRY_ENVIRONMENT', 'production' if not DEBUG else 'development'),
        release=os.getenv('APP_VERSION', 'unknown'),
    )

# ── Délai de validation automatique des commissions ──────────────────────────
COMMISSION_VALIDATION_DELAY_DAYS = int(os.getenv('COMMISSION_VALIDATION_DELAY_DAYS', '14'))

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# ── Fichiers statiques & media ────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO')
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

_log_handlers_app = ['console', 'file']

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} — {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'stream': 'ext://sys.stdout',  # UTF-8 sur Windows
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'agcspace.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'users':        {'handlers': _log_handlers_app, 'level': LOG_LEVEL, 'propagate': False},
        'products':     {'handlers': _log_handlers_app, 'level': LOG_LEVEL, 'propagate': False},
        'affiliations': {'handlers': _log_handlers_app, 'level': LOG_LEVEL, 'propagate': False},
        'orders':       {'handlers': _log_handlers_app, 'level': LOG_LEVEL, 'propagate': False},
        'cache':        {'handlers': _log_handlers_app, 'level': LOG_LEVEL, 'propagate': False},
        'security':     {'handlers': _log_handlers_app, 'level': 'WARNING', 'propagate': False},
    },
}
