# Implementation Plan: Django Admin Render Deployment

1. Установить `gunicorn` и `whitenoise` в `django_admin/venv` и обновить `django_admin/requirements.txt` (и корневой `requirements.txt`).
2. Обновить `django_admin/config/settings.py` (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `WhiteNoiseMiddleware`, `STATIC_URL`, `STATIC_ROOT`, `STORAGES`, `DATABASES`).
3. Добавить `staticfiles/` и `django_admin/staticfiles/` в `.gitignore`.
4. Выполнить `python manage.py check` и `python manage.py collectstatic --noinput`.
5. Закоммитить и отправить изменения в `origin/main`.
