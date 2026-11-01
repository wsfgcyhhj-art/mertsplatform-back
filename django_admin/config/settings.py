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

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.onrender.com']
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

DATABASES = {
    'default': dj_database_url.config(
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
    "SITE_SYMBOL": "rocket_launch",
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
                ],
            },
        ],
    },
}
