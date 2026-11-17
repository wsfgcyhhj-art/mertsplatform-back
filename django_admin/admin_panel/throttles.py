import hashlib
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.throttling import BaseThrottle
from .models import AuthRateBucket
from collections.abc import Mapping
from ipaddress import ip_address


def client_ip(request):
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
def consume_auth_attempt(ip, login=''):
    keys = [('ip:' + ip, settings.AUTH_RATE_LIMIT * 5)]
    if login:
        keys.append(('account:' + str(login).strip().lower()[:255], settings.AUTH_RATE_LIMIT))
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


class AdminLoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path.rstrip('/') == '/admin/login':
            if not consume_auth_attempt(client_ip(request), request.POST.get('username', '')):
                from django.http import HttpResponse
                return HttpResponse('Слишком много попыток входа.', status=429, headers={'Retry-After': '300'})
        return self.get_response(request)
