import os
from pathlib import Path
from django.templatetags.static import static
from django.urls import reverse_lazy
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / '.env')
_load_env_file(BASE_DIR.parent / '.env')
_load_env_file(BASE_DIR.parent / 'backend' / '.env')

import sys
import secrets
from django.core.exceptions import ImproperlyConfigured
TESTING = 'test' in sys.argv
SECRET_KEY = secrets.token_urlsafe(64) if TESTING else os.getenv("SECRET_KEY", "")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('Set SECRET_KEY to a random secret of at least 50 characters.')
DEBUG = False if TESTING else os.getenv('DEBUG', 'False').lower() in ('true', '1')
ALLOWED_HOSTS = [v.strip() for v in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if v.strip()]
if TESTING:
    ALLOWED_HOSTS.append('testserver')
RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME', '')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
CSRF_TRUSTED_ORIGINS = [v.strip().rstrip('/') for v in os.getenv('CSRF_TRUSTED_ORIGINS', FRONTEND_URL).split(',') if v.strip()]
CORS_ALLOWED_ORIGINS = [v.strip().rstrip('/') for v in os.getenv('CORS_ALLOWED_ORIGINS', FRONTEND_URL).split(',') if v.strip()]
LOCAL_FRONTEND_ORIGIN_RE = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
CORS_ALLOWED_ORIGIN_REGEXES = [
    LOCAL_FRONTEND_ORIGIN_RE,
    r"^https://[a-zA-Z0-9-]+\.vercel\.app$",
]
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax' if DEBUG else 'None'
SECURE_SSL_REDIRECT = not (TESTING or DEBUG)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Enable only behind a proxy that strips client-supplied forwarding headers.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if os.getenv('TRUST_HTTPS_PROXY') == '1' else None
SECURE_REFERRER_POLICY = 'same-origin'

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    "admin_panel",
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'admin_panel.admin_schema.AdminSchemaGuard',
    'admin_panel.throttles.AdminLoginThrottleMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

import sys

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    } if TESTING and not os.getenv('TEST_DATABASE_URL') else dj_database_url.parse(
        os.getenv('TEST_DATABASE_URL') if TESTING else os.getenv('DATABASE_URL', ''),
        conn_max_age=600,
        ssl_require=True
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

UNFOLD = {
    "SITE_TITLE": "MertsPlatform Admin",
    "SITE_HEADER": "MertsPlatform Control Center",
    "SITE_SUBHEADER": "Управление платформой и проверка ДЗ",
    "SITE_ICON": {
        "light": lambda request: static("admin_panel/favicon.svg"),
        "dark": lambda request: static("admin_panel/favicon.svg"),
    },
    "SITE_FAVICON": {
        "light": lambda request: static("admin_panel/favicon.svg"),
        "dark": lambda request: static("admin_panel/favicon.svg"),
    },
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "sizes": "any",
            "type": "image/svg+xml",
            "href": lambda request: static("admin_panel/favicon.svg"),
        },
        {
            "rel": "icon",
            "sizes": "32x32",
            "type": "image/png",
            "href": lambda request: static("admin_panel/favicon-32x32.png"),
        },
        {
            "rel": "icon",
            "sizes": "16x16",
            "type": "image/png",
            "href": lambda request: static("admin_panel/favicon-16x16.png"),
        },
        {
            "rel": "apple-touch-icon",
            "sizes": "180x180",
            "type": "image/png",
            "href": lambda request: static("admin_panel/apple-touch-icon.png"),
        },
        {
            "rel": "shortcut icon",
            "type": "image/x-icon",
            "href": lambda request: static("admin_panel/favicon.ico"),
        },
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    # Оставляем THEME=None в самом движке Unfold, чтобы рендерился встроенный переключатель Light/Dark/System,
    # а скрипт theme_init.js автоматически включает темную тему по умолчанию и добавляет кнопку в шапку!
    "THEME": None,
    "STYLES": [
        lambda request: static("admin_panel/custom.css"),
    ],
    "SCRIPTS": [
        lambda request: static("admin_panel/theme_init.js"),
    ],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Учебный процесс и ДЗ",
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": "Учебные группы",
                        "icon": "school",
                        "link": reverse_lazy("admin:admin_panel_studygroup_changelist"),
                    },
                    {
                        "title": "Проверка ДЗ",
                        "icon": "fact_check",
                        "link": reverse_lazy("admin:admin_panel_submission_changelist"),
                    },
                    {
                        "title": "Видеоуроки",
                        "icon": "smart_display",
                        "link": reverse_lazy("admin:admin_panel_lesson_changelist"),
                    },
                    {
                        "title": "Учебные задания",
                        "icon": "assignment",
                        "link": reverse_lazy("admin:admin_panel_task_changelist"),
                    },
                ],
            },
            {
                "title": "Магазин мерча",
                "separator": True,
                "items": [
                    {
                        "title": "Магазин мерча (Товары)",
                        "icon": "storefront",
                        "link": reverse_lazy("admin:admin_panel_shopproduct_changelist"),
                    },
                    {
                        "title": "Заказы мерча",
                        "icon": "shopping_bag",
                        "link": reverse_lazy("admin:admin_panel_shoporder_changelist"),
                    },
                ],
            },
            {
                "title": "Студенты и Геймификация",
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": "Доступ к платформе",
                        "icon": "key",
                        "link": reverse_lazy("admin:admin_panel_subscriptiongrant_changelist"),
                    },
                    {
                        "title": "Пользователи",
                        "icon": "group",
                        "link": reverse_lazy("admin:admin_panel_user_changelist"),
                    },
                    {
                        "title": "Бонусы и штрафы",
                        "icon": "leaderboard",
                        "link": reverse_lazy("admin:admin_panel_scoreadjustment_changelist"),
                    },
                    {
                        "title": "Каталог ачивок",
                        "icon": "emoji_events",
                        "link": reverse_lazy("admin:admin_panel_achievement_changelist"),
                    },
                    {
                        "title": "Выданные ачивки",
                        "icon": "military_tech",
                        "link": reverse_lazy("admin:admin_panel_userachievement_changelist"),
                    },
                    {
                        "title": "Архив рейтинга по месяцам",
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:admin_panel_monthlyscorearchive_changelist"),
                    },
                    {
                        "title": "Медиа-хранилище (Neon DB)",
                        "icon": "perm_media",
                        "link": reverse_lazy("admin:admin_panel_mediaasset_changelist"),
                    },
                ],
            },
        ],
    },
}


# --- API & REST FRAMEWORK CONFIGURATION ---
from datetime import timedelta

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'admin_panel.authentication.BcryptJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

SPECTACULAR_SETTINGS = {
    'ENUM_NAME_OVERRIDES': {
        'StatusEnum': 'admin_panel.models.SubmissionStatusChoices',
        'ShopOrderStatusEnum': 'admin_panel.models.ShopOrderStatus',
    },
    'TITLE': 'MertsPlatform LMS API',
    'DESCRIPTION': 'Production REST API for MertsPlatform: Authentication, Curriculum, Homework Submissions, Media Assets & Dynamic Gamification Engine.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': False,
        'displayOperationId': True,
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
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
    'idempotency-key',
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024


# Fail closed until the immutable owner IDs and Telegram webhook secret are configured.
PLATFORM_OWNER_USER_ID = os.getenv('PLATFORM_OWNER_USER_ID', '').strip()
PLATFORM_OWNER_ADMIN_ID = os.getenv('PLATFORM_OWNER_ADMIN_ID', '1').strip()
TELEGRAM_WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '').strip()
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'telegram_service': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}

TELEGRAM_OUTBOX_EAGER = not TESTING
AUTH_RATE_LIMIT = 10
AUTH_TRUSTED_PROXY_HOPS = max(0, int(os.getenv('AUTH_TRUSTED_PROXY_HOPS', '0')))
