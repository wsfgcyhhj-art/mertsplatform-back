"""Keep admin schema failures actionable without bypassing authentication."""
import logging
from django.db import ProgrammingError, OperationalError
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class AdminSchemaGuard(MiddlewareMixin):
    def process_exception(self, request, exception):
        if not (request.path.rstrip('/') in ('/admin', '/admin/login') or
                request.path.startswith('/admin/admin_panel/')):
            return None
        if not isinstance(exception, (ProgrammingError, OperationalError)):
            return None
        cause = exception.__cause__
        code = getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)
        missing = code in ('42P01', '42703') or any(
            text in str(exception).lower() for text in ('no such table:', 'no such column:'))
        if not missing:
            return None
        logging.getLogger(__name__).exception('Admin database schema is incomplete')
        return HttpResponse(
            'Админка временно недоступна: требуется обновление схемы БД. '
            'Администратору сервера: выполните python manage.py install_security.',
            status=503, content_type='text/plain; charset=utf-8', headers={'Retry-After': '60'})
