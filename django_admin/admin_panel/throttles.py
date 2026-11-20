import hashlib
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.throttling import BaseThrottle
from .models import AuthRateBucket
from collections.abc import Mapping
from ipaddress import ip_address


def client_ip(request):
    if settings.RENDER_EXTERNAL_HOSTNAME:
        try:
            return str(ip_address(request.META.get('HTTP_CF_CONNECTING_IP', '')))
        except ValueError:
            pass
    # Configure hops only for a controlled proxy chain that appends client addresses.
    hops = settings.AUTH_TRUSTED_PROXY_HOPS
    if hops:
        chain = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')
        if len(chain) >= hops:
            try:
                return str(ip_address(chain[-hops].strip()))
            except ValueError:
                pass
    return request.META.get('REMOTE_ADDR', '')


@transaction.atomic
def consume_auth_attempt(ip, login='', *, scope='auth', ip_limit=None, account_limit=None):
    resolved_ip_limit = ip_limit if ip_limit is not None else settings.AUTH_RATE_LIMIT * 5
    resolved_account_limit = account_limit if account_limit is not None else settings.AUTH_RATE_LIMIT
    ip_prefix = 'ip:' if scope == 'auth' else f'{scope}:ip:'
    keys = [(ip_prefix + ip, resolved_ip_limit)]
    if login:
        acc_prefix = 'account:' if scope == 'auth' else f'{scope}:account:'
        keys.append((acc_prefix + str(login).strip().lower()[:255], resolved_account_limit))
    for value, limit in keys:
        key = hashlib.sha256(value.encode()).hexdigest()
        bucket, _ = AuthRateBucket.objects.select_for_update().get_or_create(key=key)
        if (timezone.now() - bucket.started_at).total_seconds() >= 300:
            bucket.started_at, bucket.attempts = timezone.now(), 0
        bucket.attempts += 1
        bucket.save()
        if bucket.attempts > limit:
            return False
    return True


class AuthThrottle(BaseThrottle):
    def allow_request(self, request, view):
        identity = client_ip(request)
        login = request.data.get('login', '') if isinstance(request.data, Mapping) else ''
        return consume_auth_attempt(identity, login)

    def wait(self):
        return 300


class RefreshAuthThrottle(BaseThrottle):
    def allow_request(self, request, view):
        limit = getattr(settings, 'AUTH_REFRESH_RATE_LIMIT', settings.AUTH_RATE_LIMIT * 6)
        return consume_auth_attempt(client_ip(request), '', scope='refresh', ip_limit=limit)

    def wait(self):
        return 300


class AdminLoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path.rstrip('/') == '/admin/login':
            from django.db import ProgrammingError, OperationalError
            try:
                allowed = consume_auth_attempt(client_ip(request), request.POST.get('username', ''))
            except (ProgrammingError, OperationalError) as exc:
                from .admin_schema import AdminSchemaGuard
                response = AdminSchemaGuard(self.get_response).process_exception(request, exc)
                if response is not None:
                    return response
                raise
            if not allowed:
                from django.http import HttpResponse
                return HttpResponse('Слишком много попыток входа.', status=429, headers={'Retry-After': '300'})
        return self.get_response(request)
