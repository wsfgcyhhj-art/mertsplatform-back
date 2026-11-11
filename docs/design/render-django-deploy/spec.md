# Feature Specification: Подготовка Django Admin к деплою на Render.com

## Requirements
- **FR-001**: Установить и зафиксировать в `django_admin/requirements.txt` (и корневом `requirements.txt`) пакеты `gunicorn`, `whitenoise`, `dj-database-url`, `psycopg2-binary`, сохранив `Django`, `django-unfold`, `django-cors-headers`.
- **FR-002**: В `django_admin/config/settings.py`:
  - Настроить `ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.onrender.com', '*']` и `CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']`.
  - Подключить `'whitenoise.middleware.WhiteNoiseMiddleware'` в `MIDDLEWARE` сразу после `'django.middleware.security.SecurityMiddleware'`.
  - Настроить `STATIC_URL = '/static/'`, `STATIC_ROOT = BASE_DIR / 'staticfiles'`, `STORAGES` с `whitenoise.storage.CompressedManifestStaticFilesStorage` (и `WHITENOISE_KEEP_ONLY_HASHED_FILES` / `CompressedStaticFilesStorage` fallback).
  - Настроить `DATABASES` через `dj_database_url.config(default=os.getenv('DATABASE_URL'), conn_max_age=600, ssl_require=True)`.
- **FR-003**: Добавить `staticfiles/` и `django_admin/staticfiles/` в `.gitignore`.
- **FR-004**: Проверить `python manage.py check` и `python manage.py collectstatic --noinput`.
