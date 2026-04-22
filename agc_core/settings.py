# Auteur : Gilles - Projet : AGC Space - Module : Configuration Django
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Environnement ─────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key-change-in-prod')

# Sur Render, DEBUG doit être False — la variable d'env n'est pas définie → False par défaut
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Render injecte automatiquement le hostname du service
# Format : votre-service.onrender.com
RENDER_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME', '')

ALLOWED_HOSTS_ENV = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS_ENV if h.strip()]
if RENDER_HOSTNAME and RENDER_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_HOSTNAME)

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
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    # AGC Space apps
    'users',
    'products',
    'affiliations',
    'orders',
]

# ── Middleware ────────────────────────────────────────────────────────────────
# WhiteNoise DOIT être juste après SecurityMiddleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',      # Fichiers statiques en prod
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'agc_core.middleware.RequestLoggingMiddleware',
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

# ── Base de données ───────────────────────────────────────────────────────────
# Render fournit DATABASE_URL automatiquement pour les bases PostgreSQL attachées
# En local, fallback sur les variables individuelles
import dj_database_url

DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Production Render — dj_database_url parse l'URL complète
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=int(os.getenv('DB_CONN_MAX_AGE', '60')),
            conn_health_checks=True,
            ssl_require=not DEBUG,  # SSL obligatoire en prod, optionnel en dev
        )
    }
    # Conserver l'option de recherche full-text français
    DATABASES['default'].setdefault('OPTIONS', {})
    DATABASES['default']['OPTIONS']['options'] = '-c default_text_search_config=pg_catalog.french'
else:
    # Développement local — variables individuelles
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'agc_space'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
            'OPTIONS': {
                'options': '-c default_text_search_config=pg_catalog.french',
            },
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
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
        'TIMEOUT': int(os.getenv('CACHE_TTL', '300')),
    }
}

CACHE_TTL_PAGE_RENDER = int(os.getenv('CACHE_TTL_PAGE_RENDER', '300'))
CACHE_TTL_THEME       = int(os.getenv('CACHE_TTL_THEME', '3600'))
CACHE_TTL_PRODUCT     = int(os.getenv('CACHE_TTL_PRODUCT', '120'))

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
        'anon':     os.getenv('THROTTLE_ANON',     '100/hour'),
        'user':     os.getenv('THROTTLE_USER',     '1000/hour'),
        'login':    os.getenv('THROTTLE_LOGIN',    '10/minute'),
        'register': os.getenv('THROTTLE_REGISTER', '5/minute'),
        'validate': os.getenv('THROTTLE_VALIDATE', '30/minute'),
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
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '60'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '7'))),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'UPDATE_LAST_LOGIN': True,
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in
    os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# Sous-domaines Ngrok et Vercel acceptés via regex
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://.*\.ngrok-free\.app$',
    r'^https://.*\.ngrok-free\.dev$',
    r'^https://.*\.ngrok\.io$',
    r'^https://.*\.vercel\.app$',
    r'^https://.*\.onrender\.com$',  # Render preview deployments
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'ngrok-skip-browser-warning',
]

# ── Sécurité production ───────────────────────────────────────────────────────
if not DEBUG:
    # Render est derrière un proxy HTTPS — ne pas rediriger en interne
    # (Render gère le SSL en amont, Django reçoit du HTTP en interne)
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    SECURE_HSTS_SECONDS           = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD           = True
    SESSION_COOKIE_SECURE         = True
    CSRF_COOKIE_SECURE            = True
    SECURE_BROWSER_XSS_FILTER     = True
    SECURE_CONTENT_TYPE_NOSNIFF   = True
    X_FRAME_OPTIONS               = 'DENY'

# ── HMAC ──────────────────────────────────────────────────────────────────────
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
        send_default_pii=False,
        environment=os.getenv('SENTRY_ENVIRONMENT', 'production' if not DEBUG else 'development'),
        release=os.getenv('APP_VERSION', 'unknown'),
    )

# ── Commissions ───────────────────────────────────────────────────────────────
COMMISSION_VALIDATION_DELAY_DAYS = int(os.getenv('COMMISSION_VALIDATION_DELAY_DAYS', '14'))

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE     = 'Europe/Paris'
USE_I18N      = True
USE_TZ        = True

# ── Fichiers statiques (WhiteNoise) ──────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# WhiteNoise : compression + cache immutable pour les assets hashés
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Logging ───────────────────────────────────────────────────────────────────
# Sur Render (et tout cloud) : logs uniquement sur stdout/stderr
# Les fichiers de log ne sont pas persistants sur les instances éphémères
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO')

# En production cloud, pas de handler fichier
_IS_CLOUD = bool(os.getenv('RENDER') or os.getenv('DYNO') or not DEBUG)
_log_handlers_app = ['console'] if _IS_CLOUD else ['console', 'file']

_handlers: dict = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
        'stream': 'ext://sys.stdout',
    },
}

if not _IS_CLOUD:
    LOG_DIR = BASE_DIR / 'logs'
    LOG_DIR.mkdir(exist_ok=True)
    _handlers['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(BASE_DIR / 'logs' / 'agcspace.log'),
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} - {message}',
            'style': '{',
        },
    },
    'handlers': _handlers,
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
        'security':     {'handlers': _log_handlers_app, 'level': 'WARNING',  'propagate': False},
    },
}
