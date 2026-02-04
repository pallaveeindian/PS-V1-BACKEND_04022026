import os
from pathlib import Path
from datetime import timedelta
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# BASIC / SECURITY
# =========================
SECRET_KEY = 'DJANGO_SECRET_KEY'
DEBUG = 'True'
ALLOWED_HOSTS = ['*'] 
APISETU_CLIENT_ID = os.getenv('APISETU_CLIENT_ID', '')
APISETU_API_KEY = os.getenv('APISETU_API_KEY', '')
APISETU_SHG_LIST_URL_TEMPLATE = os.getenv('APISETU_SHG_LIST_URL_TEMPLATE', '')
APISETU_SHG_DETAIL_URL_TEMPLATE = os.getenv('APISETU_SHG_DETAIL_URL_TEMPLATE', '')
SHG_CACHE_TTL = int(os.getenv('SHG_CACHE_TTL', '300'))
CACHE_TTL = int(os.getenv('CACHE_TTL', '300'))

# =========================
# APPS
# =========================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 3rd party
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',
    'drf_yasg',

    # local
    'core',
    'epSakhi',
    'TMS',
    'LDMS',
]

# =========================
# MIDDLEWARE - add API header middleware
# =========================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'pragati_setu.middleware.ApiIdApiKeyMiddleware',  # <<-- Must be BEFORE auth middlewares
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pragati_setu.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [ BASE_DIR / 'templates' ],
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

WSGI_APPLICATION = 'pragati_setu.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =========================
# DATABASE 
# =========================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'upsrlm',
        'USER': 'techno_dev',
        'PASSWORD': 'techno@2025',
        'HOST': '204.11.58.166',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4'
        }
    }
}

# reuse DB connections for 600s
CONN_MAX_AGE = 600

# Router to keep core (master_*) read-only for this Django project
DATABASE_ROUTERS = ['core.dbrouters.MasterDBRouter']

# =========================
# CACHES
# =========================
# Use Redis (via django-redis) for default cache.
# This powers:
# - SHG / APISetu proxy caching
# - cache_page decorators
# - any other cache usage via django.core.cache.cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        # Password 'techno@2025' -> 'techno%402025' in URL
        'LOCATION': 'redis://:techno%402025@127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 2,
            'SOCKET_TIMEOUT': 2,
        },
        'KEY_PREFIX': 'pragati_setu',
    }
}

# =========================
# AUTH
# =========================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = (
    'core.backends.MasterUserBackend',
)

# =========================
# I18N / TIMEZONE
# =========================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# =========================
# STATIC / MEDIA
# =========================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
os.makedirs(MEDIA_ROOT, exist_ok=True)

# =========================
# REST FRAMEWORK & JWT
# =========================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
}

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-api-id',
    'x-api-key',
]

# Upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

# =========================
# API header credentials (used by middleware)
# Map of api_id -> api_key
# In production store in DB/env; this is here for quick start
# =========================
ALLOWED_API_CREDENTIALS = {
    "BDO_PMUser.TH_test.co.in": 'wFR8IpSeNMawCF4RPLXit1POGuQAJTSmRexBBOwO'
}

# Simple admin email
DEFAULT_FROM_EMAIL = 'webmaster@localhost'
