"""Isolated browser-test backend: disposable SQLite, no external calls or real users."""
import os
import sys
import tempfile

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
sys.argv = ['manage.py', 'test']

import django
from django.conf import settings

with tempfile.TemporaryDirectory(prefix='merts-browser-') as directory:
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': directory + '/test.sqlite3'}}
    settings.CSRF_TRUSTED_ORIGINS = ['http://localhost:5173']
    settings.TELEGRAM_OUTBOX_EAGER = False
    django.setup()
    from django.core.management import call_command
    from admin_panel.test_support import create_schema, create_user
    call_command('migrate', verbosity=0)
    create_schema()
    student = create_user(login='browser_student', has_subscription=True, group_number='js-01', must_change_password=True)
    student.set_password('Temporary-For-Browser-2026!')
    student.save()
    call_command('runserver', '127.0.0.1:8000', use_reloader=False)
