from django.test import SimpleTestCase
from django.contrib import admin
from admin_panel.models import Lesson, User
from admin_panel.admin import LessonAdmin
from admin_panel.serializers import ChangePasswordSerializer
from admin_panel.services.media_service import save_optimized_media_asset
from unittest.mock import patch

class SecurityRegressionTests(SimpleTestCase):
    def test_untrusted_forwarded_ip_is_ignored(self):
        from django.test import RequestFactory, override_settings
        from admin_panel.throttles import client_ip
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='198.51.100.2, 203.0.113.3')
        with override_settings(AUTH_TRUSTED_PROXY_HOPS=0):
            self.assertEqual(client_ip(request), '192.0.2.1')
        with override_settings(AUTH_TRUSTED_PROXY_HOPS=1):
            self.assertEqual(client_ip(request), '203.0.113.3')

    def test_correct_lesson_admin_registered(self):
        self.assertIsInstance(admin.site._registry[Lesson], LessonAdmin)
        self.assertIn('youtube_id', LessonAdmin.readonly_fields)
        from admin_panel.admin import SearchableGroupWidget
        self.assertIsInstance(LessonAdmin.form.base_fields['group_number'].widget, SearchableGroupWidget)

    def test_svg_rejected_before_database(self):
        with patch('admin_panel.services.media_service.MediaAsset.objects.create') as create:
            with self.assertRaises(ValueError):
                save_optimized_media_asset.__wrapped__(b'<svg><script/></svg>', 'image/svg+xml')
            create.assert_not_called()

    def test_common_password_rejected(self):
        serializer = ChangePasswordSerializer(data={'currentPassword': 'old', 'newPassword': 'password123'})
        self.assertFalse(serializer.is_valid())

    def test_legacy_sha256_bcrypt_accepts_plain_password(self):
        import hashlib, bcrypt
        password = 'Valid-legacy-pass-2026'
        user = User(password_hash=bcrypt.hashpw(hashlib.sha256(password.encode()).hexdigest().encode(), bcrypt.gensalt()).decode())
        self.assertTrue(user.check_password(password))

    def test_icon_widget_escapes_attribute_injection(self):
        from admin_panel.admin import PresetIconGalleryWidget
        payload = '\"><img src=x onerror=alert(1)>'
        html = str(PresetIconGalleryWidget().render('icon', payload))
        self.assertNotIn(payload, html)
        self.assertIn('&lt;img', html)

    def test_image_pixel_limit_checked_before_decode(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (20, 20)).save(buf, format='PNG')
        with patch('admin_panel.services.media_service.MAX_PIXELS', 100):
            with self.assertRaises(ValueError):
                save_optimized_media_asset.__wrapped__(buf.getvalue(), 'image/png')


from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.db import connection, connections, close_old_connections, transaction
from admin_panel.test_support import create_schema, clear_data, create_user, subscribe
from admin_panel.models import Lesson, Task, Submission, ScoreAdjustment, TelegramOutbox, TelegramUpdate, Session, MediaAsset, StudyGroup
from admin_panel.authentication import generate_tokens_for_user, rotate_refresh
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta


class SecurityIntegrationTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        self.user = create_user(login='student', has_subscription=True, group_number='js-01')
        self.user.set_password('Strong-Pass-2026!')
        self.user.save()
        self.client = APIClient()
        self.access, self.refresh, _ = generate_tokens_for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.access)

    def test_logout_revokes_access_and_refresh(self):
        self.assertEqual(self.client.get('/api/v1/users/me').status_code, 200)
        self.client.post('/api/v1/auth/logout', {'refreshToken': self.refresh}, format='json')
        self.assertEqual(self.client.get('/api/v1/users/me').status_code, 401)
        self.assertIsNone(rotate_refresh(self.refresh))

    def test_password_change_revokes_all_sessions(self):
        response = self.client.put('/api/v1/users/me/password', {'currentPassword': 'Strong-Pass-2026!', 'newPassword': 'Different-Strong-2026!'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/users/me').status_code, 401)
        self.assertIsNone(rotate_refresh(self.refresh))

    def test_stale_profile_save_does_not_restore_old_password(self):
        fresh = User.objects.get(pk=self.user.pk)
        fresh.set_password('New-Password-After-Auth-2026!')
        fresh.save()
        self.client.force_authenticate(self.user)  # Simulate auth before a concurrent password change.
        self.assertEqual(self.client.patch('/api/v1/users/me', {'name': 'Updated'}, format='json').status_code, 200)
        fresh.refresh_from_db()
        self.assertTrue(fresh.check_password('New-Password-After-Auth-2026!'))

    def test_refresh_is_single_use_and_stored_as_digest(self):
        self.assertFalse(Session.objects.filter(refresh_token=self.refresh).exists())
        self.assertIsNotNone(rotate_refresh(self.refresh))
        self.assertIsNone(rotate_refresh(self.refresh))

    def test_logout_revokes_session_after_concurrent_rotation(self):
        from admin_panel.authentication import revoke_session
        _, rotated_refresh, _ = rotate_refresh(self.refresh)
        revoke_session(self.refresh, self.access)
        self.assertIsNone(rotate_refresh(rotated_refresh))
        self.assertEqual(self.client.get('/api/v1/users/me').status_code, 401)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_refresh_only_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return rotate_refresh(self.refresh) is not None
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(run), pool.submit(run)
            self.assertEqual(sum([a.result(), b.result()]), 1)

    @override_settings(AUTH_RATE_LIMIT=2)
    def test_login_rate_limit(self):
        client = APIClient()
        payload = {'login': 'student', 'password': 'wrong'}
        self.assertEqual(client.post('/api/v1/auth/login', payload).status_code, 401)
        self.assertEqual(client.post('/api/v1/auth/login', payload).status_code, 401)
        self.assertEqual(client.post('/api/v1/auth/login', payload).status_code, 429)

    def test_foreign_submission_and_admin_denied(self):
        other = create_user(login='other', has_subscription=True)
        task = Task.objects.create(title='Task', topic='Python', month=1)
        sub = Submission.objects.create(user=other, task=task, solution_link='https://example.org', reviewer_comment='private')
        self.assertEqual(self.client.get('/api/v1/submissions/' + sub.pk).status_code, 403)
        self.assertNotIn(sub.pk, str(self.client.get('/api/v1/submissions').data))
        self.assertEqual(self.client.patch('/api/v1/submissions/' + sub.pk, {'score': 10}).status_code, 403)
        for path in ('users', 'stats'):
            self.assertEqual(self.client.get('/api/v1/admin/' + path).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/admin/score-adjustments', {}).status_code, 403)
        self.client.patch('/api/v1/users/me', {'id': other.pk, 'name': 'changed'}, format='json')
        other.refresh_from_db()
        self.assertNotEqual(other.name, 'changed')

    def test_subscription_revoked_even_if_user_flag_remains(self):
        from admin_panel.models import SubscriptionGrant
        SubscriptionGrant.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.client.get('/api/v1/tasks').status_code, 403)

    def test_latest_accepted_score_only(self):
        task = Task.objects.create(title='Task', topic='Python', month=1)
        Submission.objects.create(user=self.user, task=task, version=1, status='ACCEPTED', score=5)
        Submission.objects.create(user=self.user, task=task, version=2, status='ACCEPTED', score=8)
        self.assertEqual(self.user.calculate_total_score(), 8)
        self.assertEqual(self.user.accepted_tasks_count(), 1)

    def test_media_limits_and_other_owner_preserved(self):
        import io
        from PIL import Image
        from admin_panel.services.media_service import save_optimized_media_asset
        other = MediaAsset.objects.create(kind='AVATAR', owner_id='other', mime_type='image/webp', data=b'x', size_bytes=1)
        with self.assertRaises(ValueError):
            save_optimized_media_asset(b'x' * (2 * 1024**2 + 1), 'image/png', 'AVATAR', self.user.pk)
        buf = io.BytesIO()
        Image.new('RGB', (8, 8)).save(buf, format='PNG')
        save_optimized_media_asset(buf.getvalue(), 'image/png', 'AVATAR', self.user.pk)
        self.assertTrue(MediaAsset.objects.filter(pk=other.pk).exists())

    def test_outbox_rollback_and_retry(self):
        from admin_panel.services.outbox_service import enqueue, drain
        try:
            with transaction.atomic():
                enqueue('123', 'rollback', dedupe_key='rollback')
                raise ValueError()
        except ValueError:
            pass
        self.assertFalse(TelegramOutbox.objects.exists())
        enqueue('123', 'retry', dedupe_key='retry')
        enqueue('123', 'retry', dedupe_key='retry')
        with patch('admin_panel.services.telegram_service.send_telegram_message', return_value=False):
            self.assertEqual(drain(), 0)
        item = TelegramOutbox.objects.get()
        self.assertEqual(item.attempts, 1)
        item.available_at = timezone.now() - timedelta(seconds=1)
        item.save()
        with patch('admin_panel.services.telegram_service.send_telegram_message', return_value=True):
            self.assertEqual(drain(), 1)
        item.refresh_from_db()
        self.assertEqual(item.status, 'sent')
        self.assertEqual(item.payload, {})

    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_duplicate_webhook_processed_once(self):
        client = APIClient()
        data = {'update_id': 123, 'message': {'chat': {'id': 77, 'type': 'private'}, 'from': {'id': 77, 'username': 'student_77'}, 'text': '/help'}}
        for _ in range(2):
            self.assertEqual(client.post('/api/v1/telegram/webhook', data, format='json', HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret').status_code, 200)
        self.assertEqual(TelegramUpdate.objects.count(), 1)
        self.assertEqual(TelegramOutbox.objects.count(), 1)

    def test_csrf_required_for_cookie_auth_endpoints(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/v1/auth/login', {'login': 'student', 'password': 'Strong-Pass-2026!'}).status_code, 403)

    def test_cors_preflight_and_cookie_refresh_from_local_origin(self):
        client = APIClient(enforce_csrf_checks=True)
        for origin in ('http://localhost:5173', 'http://127.0.0.1:8080', 'https://merts-preview.vercel.app'):
            response = client.options('/api/v1/auth/login', secure=True, HTTP_ORIGIN=origin,
                                      HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                                      HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization, x-csrftoken')
            self.assertEqual(response['Access-Control-Allow-Origin'], origin)
            self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')

        origin = 'http://localhost:5174'
        csrf = client.get('/api/v1/auth/csrf', secure=True, HTTP_ORIGIN=origin).json()['csrfToken']
        login = client.post('/api/v1/auth/login', {'login': 'student', 'password': 'Strong-Pass-2026!'},
                            secure=True, HTTP_ORIGIN=origin, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.cookies['refreshToken']['secure'])
        self.assertEqual(login.cookies['refreshToken']['samesite'], 'None')
        blocked = client.post('/api/v1/auth/refresh', {}, secure=True,
                              HTTP_ORIGIN='https://untrusted-preview.vercel.app', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(blocked.status_code, 403)
        refresh = client.post('/api/v1/auth/refresh', {}, secure=True, HTTP_ORIGIN=origin, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(refresh.status_code, 200)
        profile = client.get('/api/v1/users/me', secure=True, HTTP_ORIGIN='https://merts-preview.vercel.app',
                             HTTP_AUTHORIZATION='Bearer ' + refresh.json()['accessToken'])
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile['Access-Control-Allow-Origin'], 'https://merts-preview.vercel.app')

    @override_settings(AUTH_RATE_LIMIT=1)
    def test_admin_login_is_rate_limited(self):
        from django.test import RequestFactory
        from django.http import HttpResponse
        from admin_panel.throttles import AdminLoginThrottleMiddleware
        middleware = AdminLoginThrottleMiddleware(lambda r: HttpResponse('login'))
        request = RequestFactory().post('/admin/login/', {'username': 'owner'})
        self.assertEqual(middleware(request).status_code, 200)
        self.assertEqual(middleware(request).status_code, 429)

    def test_score_adjustment_retry_does_not_award_twice(self):
        mentor = create_user(login='mentor', role='ADMIN')
        self.client.force_authenticate(mentor)
        data = {'userId': self.user.pk, 'amount': 10, 'reason': 'Bonus', 'month': 1}
        for _ in range(2):
            self.assertEqual(self.client.post('/api/v1/admin/score-adjustments', data, format='json', HTTP_IDEMPOTENCY_KEY='bonus-one').status_code, 201)
        self.assertEqual(self.user.calculate_total_score(), 10)
        data['amount'] = 20
        self.assertEqual(self.client.post('/api/v1/admin/score-adjustments', data, format='json', HTTP_IDEMPOTENCY_KEY='bonus-one').status_code, 409)

    def test_review_rejects_invalid_score_status_and_url(self):
        mentor = create_user(login='reviewer', role='ADMIN')
        self.client.force_authenticate(mentor)
        task = Task.objects.create(title='Review task', topic='Topic', max_score=10)
        sub = Submission.objects.create(user=self.user, task=task)
        for data in ({'score': -1}, {'score': 11}, {'score': 1.5}, {'status': 'UNKNOWN'}, {'voiceFeedbackUrl': 'javascript:alert(1)'}):
            self.assertEqual(self.client.patch('/api/v1/submissions/' + sub.pk, data, format='json').status_code, 400)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'SENT')

    def test_notification_events_persist_once_and_hide_payload(self):
        from admin_panel.models import Achievement, UserAchievement
        self.user.telegram_chat_id = '123'
        self.user.save()
        achievement = Achievement.objects.create(title='Manual', description='test', trigger_type='MANUAL')
        lesson = Lesson.objects.create(title='Lesson', month=1, group_number='js-01', youtube_id='abcdefghijk')
        task = Task.objects.create(title='Task', topic='Topic', month=1, group_number='js-01')
        sub = Submission.objects.create(user=self.user, task=task, status='ACCEPTED', score=5)
        sub.save()  # Unchanged review must not enqueue again.
        ScoreAdjustment.objects.create(user=self.user, admin=self.user, amount=2, reason='Bonus', month=1)
        UserAchievement.objects.create(user=self.user, achievement=achievement)
        self.user.current_month = 2
        self.user.save()
        self.assertEqual(TelegramOutbox.objects.count(), 6)
        self.assertTrue(all('encrypted' in p for p in TelegramOutbox.objects.values_list('payload', flat=True)))
        self.assertNotIn(lesson.title, str(list(TelegramOutbox.objects.values_list('payload', flat=True))))

    def test_bound_telegram_survives_username_removal_and_reuse(self):
        from admin_panel.services.subscription_service import handle_subscription_start, grant_subscription
        from admin_panel.models import SubscriptionGrant, TelegramIdentity
        group = StudyGroup.objects.get(name='js-01')
        grant_subscription('new_student', group, None, 'owner')
        handle_subscription_start('444', 'new_student')
        handle_subscription_start('555', 'new_student')
        self.assertIn('Telegram успешно подключён', handle_subscription_start('444', None))
        self.assertEqual(SubscriptionGrant.objects.get(telegram_username='new_student').telegram_user_id, '444')
        self.assertTrue(TelegramIdentity.objects.filter(pk='444').exists())

    def test_expired_subscription_and_archived_group_denied(self):
        from admin_panel.models import SubscriptionGrant
        grant = SubscriptionGrant.objects.get(user=self.user)
        grant.expires_at = timezone.now() - timedelta(seconds=1)
        grant.save()
        self.assertEqual(self.client.get('/api/v1/tasks').status_code, 403)
        grant.expires_at = None
        grant.save()
        grant.group.is_active = False
        grant.group.save()
        self.assertEqual(self.client.get('/api/v1/tasks').status_code, 403)

    def test_curriculum_lists_hide_other_groups_and_future_months(self):
        for endpoint, model, fields in (
            ('lessons', Lesson, {'video_link': 'https://example.org/lesson'}),
            ('tasks', Task, {'topic': 'Topic'}),
        ):
            with self.subTest(endpoint=endpoint):
                own = model.objects.create(title='Own', month=1, group_number='js-01', **fields)
                shared = model.objects.create(title='Shared', month=1, group_number='ALL', **fields)
                model.objects.create(title='Other group', month=1, group_number='py-01', **fields)
                model.objects.create(title='Future', month=2, group_number='js-01', **fields)

                response = self.client.get(f'/api/v1/{endpoint}', {'month': 'all', 'groupNumber': 'py-01'})
                self.assertEqual(response.status_code, 200)
                self.assertCountEqual([item['id'] for item in response.json()[endpoint]], [own.pk, shared.pk])

    def test_voice_feedback_change_enqueues_once(self):
        import json
        from admin_panel.services.outbox_service import cipher

        self.user.telegram_chat_id = '123'
        self.user.save()
        mentor = create_user(login='voice-reviewer', role='ADMIN')
        task = Task.objects.create(title='Voice task', topic='Topic')
        sub = Submission.objects.create(user=self.user, task=task, status='IN_REVIEW')
        TelegramOutbox.objects.all().delete()
        self.client.force_authenticate(mentor)
        payload = {'voiceFeedbackUrl': 'https://example.org/feedback.ogg'}
        for _ in range(2):
            self.assertEqual(self.client.patch('/api/v1/submissions/' + sub.pk, payload, format='json').status_code, 200)
        self.assertEqual(TelegramOutbox.objects.count(), 1)
        message = TelegramOutbox.objects.get().payload['encrypted']
        self.assertIn('https://example.org/feedback.ogg', json.loads(cipher().decrypt(message))['text'])

    @override_settings(TELEGRAM_OUTBOX_EAGER=True)
    def test_telegram_voice_file_is_sent_once_after_commit(self):
        from admin_panel.services import telegram_service

        self.user.telegram_chat_id = '123'
        self.user.save()
        task = Task.objects.create(title='Voice task', topic='Topic')
        sub = Submission.objects.create(user=self.user, task=task)
        sub.status = 'IN_REVIEW'
        sub.voice_feedback_url = 'telegram_file-id'
        with patch.object(telegram_service, 'get_bot_token', return_value='test-token'), \
                patch.object(telegram_service.httpx, 'Client') as client:
            send = client.return_value.__enter__.return_value.post
            send.return_value.status_code = 200
            send.return_value.json.return_value = {'ok': True}
            with transaction.atomic():
                sub.save()
                send.assert_not_called()
            sub.save()
        self.assertEqual([call.args[0].rsplit('/', 1)[-1] for call in send.call_args_list],
                         ['sendMessage', 'sendVoice'])
        self.assertEqual(send.call_args.kwargs['json'], {'chat_id': '123', 'voice': 'telegram_file-id'})

    def test_security_installer_is_repeatable(self):
        from django.core.management import call_command
        from io import StringIO
        from admin_panel.models import TelegramIdentity, AuthRateBucket
        # Recreate the pre-security schema to exercise real DDL, not just no-ops.
        with connection.schema_editor() as editor:
            editor.remove_field(ScoreAdjustment, ScoreAdjustment._meta.get_field('idempotency_key'))
            editor.remove_constraint(Submission, Submission._meta.constraints[0])
            for model in (AuthRateBucket, TelegramUpdate, TelegramOutbox):
                editor.delete_model(model)
            field = TelegramIdentity._meta.get_field('username')
            legacy = field.clone()
            legacy.set_attributes_from_name('username')
            legacy.model = TelegramIdentity
            legacy.null = False
            editor.alter_field(TelegramIdentity, field, legacy)
        for _ in range(2):
            call_command('install_security', stdout=StringIO())
        self.assertEqual(Session.objects.count(), 1)
        TelegramIdentity.objects.create(telegram_user_id='legacy', username=None)
