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

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure--z%w@n92g0x!2qz3+n=ak-5d0f4!#&o+xb(&#e+!=8(vj_3d7u')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver', '.onrender.com']

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.getenv('RENDER_EXTERNAL_HOSTNAME', ''))

CSRF_TRUSTED_ORIGINS = [
    'https://*.onrender.com',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

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
    } if 'test' in sys.argv else dj_database_url.config(
        default=os.getenv('DATABASE_URL'),
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
                        "title": "Учебные группы (Groups)",
                        "icon": "school",
                        "link": reverse_lazy("admin:admin_panel_studygroup_changelist"),
                    },
                    {
                        "title": "Проверка ДЗ (Submissions)",
                        "icon": "fact_check",
                        "link": reverse_lazy("admin:admin_panel_submission_changelist"),
                    },
                    {
                        "title": "Видеоуроки (Lessons)",
                        "icon": "smart_display",
                        "link": reverse_lazy("admin:admin_panel_lesson_changelist"),
                    },
                    {
                        "title": "Учебные задания (Tasks)",
                        "icon": "assignment",
                        "link": reverse_lazy("admin:admin_panel_task_changelist"),
                    },
                ],
            },
            {
                "title": "Студенты и Геймификация",
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": "Пользователи (Users)",
                        "icon": "group",
                        "link": reverse_lazy("admin:admin_panel_user_changelist"),
                    },
                    {
                        "title": "Бонусы и штрафы (Scores)",
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
        'rest_framework.permissions.AllowAny',
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
    'TITLE': 'MertsPlatform LMS API',
    'DESCRIPTION': 'Production REST API for MertsPlatform: Authentication, Curriculum, Homework Submissions, Media Assets & Dynamic Gamification Engine.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

CORS_ALLOW_ALL_ORIGINS = True
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
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
