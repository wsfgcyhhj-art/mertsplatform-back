import io
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import OperationalError, connection
from django.db.models import Sum
from django.test import RequestFactory, SimpleTestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.test import APIClient

from admin_panel.admin import (
    AchievementAdmin,
    MediaAssetAdmin,
    StudyGroupAdmin,
    SubmissionAdmin,
    TaskAdmin,
    UserAdmin,
)
from admin_panel.api_utils import expand_dual_case, paginate_list_or_qs
from admin_panel.authentication import generate_tokens_for_user
from admin_panel.models import (
    Achievement,
    Lesson,
    MediaAsset,
    MonthlyScoreArchive,
    PlatformSetting,
    RoleChoices,
    ScoreAdjustment,
    StudyGroup,
    Submission,
    SubmissionStatusChoices,
    Task,
    TelegramOutbox,
    TriggerTypeChoices,
    User,
    UserAchievement,
)
from admin_panel.services import outbox_service
from admin_panel.services.settings_service import (
    cache_delete_safe,
    cache_get_safe,
    cache_set_safe,
    invalidate_settings_cache,
    validate_setting_value,
)
from admin_panel.services.telegram_service import (
    is_last_telegram_error_permanent,
    run_telegram_polling,
    send_telegram_message,
)
from admin_panel.test_support import clear_data, create_schema, create_user


def _mock_httpx_response(status_code: int, payload: dict, text: str = ''):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text or json.dumps(payload)
    resp.json.return_value = payload
    return resp


def _superuser_request(method='GET', path='/'):
    req = getattr(RequestFactory(), method.lower())(path)
    req.user = SimpleNamespace(
        id=1,
        pk=1,
        is_active=True,
        is_authenticated=True,
        is_superuser=True,
        is_staff=True,
        has_perm=lambda *a, **k: True,
    )
    return req


class AuditUnitRegressionTests(SimpleTestCase):
    def test_runtime_defaults_database_cache_outbox_polling_and_proxy_hops(self):
        env = dict(
            os.environ,
            SECRET_KEY='x' * 64,
            DATABASE_URL='postgresql://user:password@db/app',
        )
        for key in ('TELEGRAM_MODE', 'TELEGRAM_OUTBOX_EAGER', 'AUTH_TRUSTED_PROXY_HOPS', 'TRUST_HTTPS_PROXY'):
            env.pop(key, None)

        code = (
            'import json; from unittest.mock import patch\n'
            'with patch("pathlib.Path.read_text", return_value=""):\n'
            ' import config.settings as s\n'
            ' print(json.dumps({'
            '"cache_backend": s.CACHES["default"]["BACKEND"],'
            '"cache_location": s.CACHES["default"]["LOCATION"],'
            '"telegram_mode": s.TELEGRAM_MODE,'
            '"outbox_eager": s.TELEGRAM_OUTBOX_EAGER,'
            '"proxy_hops": s.AUTH_TRUSTED_PROXY_HOPS,'
            '"testing": s.TESTING'
            '}))\n'
        )
        backend_dir = Path(__file__).resolve().parents[1]
        data = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=backend_dir, env=env, text=True))
        self.assertFalse(data['testing'])
        self.assertEqual(data['cache_backend'], 'django.core.cache.backends.db.DatabaseCache')
        self.assertEqual(data['cache_location'], 'django_cache')
        self.assertEqual(data['telegram_mode'], 'polling')
        self.assertFalse(data['outbox_eager'])
        self.assertEqual(data['proxy_hops'], 1)

        env_bad = dict(env, TELEGRAM_MODE='invalid_mode')
        code_mode = (
            'import json; from unittest.mock import patch\n'
            'with patch("pathlib.Path.read_text", return_value=""):\n'
            ' import config.settings as s\n'
            ' print(json.dumps(s.TELEGRAM_MODE))\n'
        )
        mode = json.loads(
            subprocess.check_output([sys.executable, '-c', code_mode], cwd=backend_dir, env=env_bad, text=True)
        )
        self.assertEqual(mode, 'polling')

    def test_cache_safe_wrappers_ignore_db_unavailable_errors(self):
        err = OperationalError('no such table: django_cache')
        with (
            patch('admin_panel.services.settings_service.cache.get', side_effect=err),
            patch('admin_panel.services.settings_service.cache.set', side_effect=err),
            patch('admin_panel.services.settings_service.cache.delete', side_effect=err),
        ):
            self.assertIsNone(cache_get_safe('missing'))
            cache_set_safe('k', 'v', 60)
            cache_delete_safe('k')

    def test_platform_setting_is_public_default_denylist_and_telegram_html(self):
        self.assertFalse(PlatformSetting._meta.get_field('is_public').default)

        for secret_key in ('bot_token', 'webhook_secret', 'api_key', 'db_password'):
            with self.assertRaises(ValidationError):
                validate_setting_value(secret_key, 'secret-val', 'string', is_public=True)
            self.assertEqual(validate_setting_value(secret_key, 'secret-val', 'string', is_public=False), 'secret-val')

        valid_html = '<b>Ок</b> <a href="https://example.com">link</a> <code>{title}</code>'
        self.assertEqual(validate_setting_value('tg_template_new_task', valid_html, 'text'), valid_html)

        bad_samples = (
            '<script>x</script>',
            '<div>x</div>',
            '<br/>',
            '<b>unclosed',
            '<b><i></b></i>',
            '<a href="javascript:alert(1)">x</a>',
        )
        for sample in bad_samples:
            with self.subTest(sample=sample):
                with self.assertRaises(ValidationError):
                    validate_setting_value('tg_template_new_task', sample, 'text')

    def test_expand_dual_case_limits_and_unpaginated_cap(self):
        nested = 'leaf'
        for _ in range(18):
            nested = {'a': nested}
        with self.assertRaises(ParseError):
            expand_dual_case(nested)

        with self.assertRaises(ParseError):
            expand_dual_case({'a': list(range(10005))})

        page_meta, items = paginate_list_or_qs(Request(RequestFactory().get('/')), list(range(250)))
        self.assertIsNone(page_meta)
        self.assertEqual(len(items), 200)

    @override_settings(TELEGRAM_BOT_TOKEN='123:test-token')
    def test_telegram_html_fallback_permanent_classification_and_polling_lifecycle(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = [
            _mock_httpx_response(400, {'ok': False, 'error_code': 400, 'description': "Bad Request: can't parse entities"}),
            _mock_httpx_response(200, {'ok': True}),
        ]
        with patch('admin_panel.services.telegram_service.httpx.Client') as client_cls:
            client_cls.return_value.__enter__.return_value = mock_client
            self.assertTrue(send_telegram_message('123', '<b>bad'))
        self.assertEqual(mock_client.post.call_count, 2)
        self.assertIn('parse_mode', mock_client.post.call_args_list[0].kwargs['json'])
        self.assertNotIn('parse_mode', mock_client.post.call_args_list[1].kwargs['json'])

        mock_client_403 = MagicMock()
        mock_client_403.post.return_value = _mock_httpx_response(
            403, {'ok': False, 'error_code': 403, 'description': 'Forbidden: bot was blocked by the user'}
        )
        with patch('admin_panel.services.telegram_service.httpx.Client') as client_cls:
            client_cls.return_value.__enter__.return_value = mock_client_403
            self.assertFalse(send_telegram_message('123', 'hi'))
        self.assertTrue(is_last_telegram_error_permanent())

        mock_client_500 = MagicMock()
        mock_client_500.post.return_value = _mock_httpx_response(500, {'ok': False, 'description': 'Internal error'})
        with patch('admin_panel.services.telegram_service.httpx.Client') as client_cls:
            client_cls.return_value.__enter__.return_value = mock_client_500
            self.assertFalse(send_telegram_message('123', 'hi'))
        self.assertFalse(is_last_telegram_error_permanent())

        with (
            override_settings(TELEGRAM_MODE='webhook'),
            patch('admin_panel.services.telegram_service.httpx.Client') as client_cls,
        ):
            self.assertEqual(run_telegram_polling(max_cycles=1), 0)
            client_cls.assert_not_called()

        poll_client = MagicMock()
        poll_client.post.return_value = _mock_httpx_response(200, {'ok': True})
        poll_client.get.return_value = _mock_httpx_response(409, {'ok': False}, text='Conflict')
        with (
            override_settings(TELEGRAM_MODE='polling'),
            patch('admin_panel.services.telegram_service.httpx.Client') as client_cls,
            patch('time.sleep'),
        ):
            client_cls.return_value.__enter__.return_value = poll_client
            self.assertEqual(run_telegram_polling(max_cycles=1), 0)
        self.assertIn('/deleteWebhook', poll_client.post.call_args.args[0])
        self.assertEqual(poll_client.post.call_args.kwargs['json'], {'drop_pending_updates': False})
        self.assertIn('/getUpdates', poll_client.get.call_args.args[0])

    def test_openapi_schema_has_no_untyped_success_responses(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        checked = 0
        for path, methods in schema.get('paths', {}).items():
            for method, operation in methods.items():
                if not isinstance(operation, dict):
                    continue
                for code, resp in (operation.get('responses') or {}).items():
                    if str(code) not in ('200', '201'):
                        continue
                    json_media = (resp.get('content') or {}).get('application/json')
                    if not json_media:
                        continue
                    checked += 1
                    resp_schema = json_media.get('schema')
                    self.assertTrue(resp_schema, f'{method.upper()} {path} {code} has empty response schema')
                    self.assertNotEqual(
                        resp_schema,
                        {'type': 'object', 'additionalProperties': {}},
                        f'{method.upper()} {path} {code} uses untyped dict schema',
                    )
        self.assertGreater(checked, 0)


class AuditIntegrationRegressionTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        self.group = StudyGroup.objects.create(name='js-01', month=1)
        self.owner = create_user(login='owner', role=RoleChoices.ADMIN, has_subscription=True, group_number='js-01')
        self.owner.set_password('Owner-Pass-2026!')
        self.owner.save()

        self.mentor = create_user(login='mentor', role=RoleChoices.ADMIN, has_subscription=True, group_number='js-01')
        self.mentor.set_password('Mentor-Pass-2026!')
        self.mentor.save()

        self.student = create_user(
            login='student',
            role=RoleChoices.STUDENT,
            has_subscription=True,
            group_number='js-01',
            current_month=1,
        )
        self.student.set_password('Strong-Pass-2026!')
        self.student.save()

        self.owner_client = APIClient()
        self.owner_access, _, _ = generate_tokens_for_user(self.owner)
        self.owner_client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.owner_access)

        self.mentor_client = APIClient()
        self.mentor_access, _, _ = generate_tokens_for_user(self.mentor)
        self.mentor_client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.mentor_access)

        self.student_client = APIClient()
        self.student_access, self.student_refresh, _ = generate_tokens_for_user(self.student)
        self.student_client.credentials(HTTP_AUTHORIZATION='Bearer ' + self.student_access)

    def test_install_base_schema_idempotent(self):
        buf1, buf2 = io.StringIO(), io.StringIO()
        call_command('install_base_schema', stdout=buf1)
        call_command('install_base_schema', stdout=buf2)
        self.assertIn('created 0 tables', buf2.getvalue())

    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_telegram_webhook_mode_gate_and_secret_order(self):
        client = APIClient()
        payload = {'update_id': 999, 'message': {'chat': {'id': 77, 'type': 'private'}, 'text': '/help'}}

        with override_settings(TELEGRAM_MODE='polling'):
            bad_secret = client.post(
                '/api/v1/telegram/webhook', payload, format='json', HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='wrong'
            )
            self.assertEqual(bad_secret.status_code, 403)
            conflict = client.post(
                '/api/v1/telegram/webhook', payload, format='json', HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret'
            )
            self.assertEqual(conflict.status_code, 409)
            self.assertFalse(conflict.json()['ok'])

        with override_settings(TELEGRAM_MODE='disabled'):
            disabled = client.post(
                '/api/v1/telegram/webhook', payload, format='json', HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret'
            )
            self.assertEqual(disabled.status_code, 409)

        with (
            override_settings(TELEGRAM_MODE='webhook'),
            patch('admin_panel.views.telegram_views.process_telegram_update') as proc,
        ):
            ok = client.post(
                '/api/v1/telegram/webhook', payload, format='json', HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret'
            )
            self.assertEqual(ok.status_code, 200)
            proc.assert_called_once()

    @override_settings(TELEGRAM_BOT_TOKEN='123:test-token', TELEGRAM_OUTBOX_EAGER=False)
    def test_outbox_permanent_error_fails_immediately_and_transient_retries(self):
        outbox_service.enqueue('100', 'perm-fail', dedupe_key='perm-1')
        outbox_service.enqueue('100', 'temp-retry', dedupe_key='temp-1')
        perm = TelegramOutbox.objects.get(dedupe_key='perm-1')
        temp = TelegramOutbox.objects.get(dedupe_key='temp-1')

        mock_403 = MagicMock()
        mock_403.post.return_value = _mock_httpx_response(403, {'ok': False, 'error_code': 403, 'description': 'Forbidden'})
        with patch('admin_panel.services.telegram_service.httpx.Client') as client_cls:
            client_cls.return_value.__enter__.return_value = mock_403
            self.assertFalse(outbox_service.deliver(perm.pk))
        perm.refresh_from_db()
        self.assertEqual(perm.status, 'failed')
        self.assertEqual(perm.attempts, 1)

        mock_500 = MagicMock()
        mock_500.post.return_value = _mock_httpx_response(500, {'ok': False, 'description': 'Server Error'})
        with patch('admin_panel.services.telegram_service.httpx.Client') as client_cls:
            client_cls.return_value.__enter__.return_value = mock_500
            self.assertFalse(outbox_service.deliver(temp.pk))
        temp.refresh_from_db()
        self.assertEqual(temp.status, 'pending')
        self.assertEqual(temp.attempts, 1)

        with patch('admin_panel.management.commands.deliver_telegram.drain', side_effect=RuntimeError('db glitch')):
            call_command('deliver_telegram', '--once')

    @override_settings(AUTH_RATE_LIMIT=1, AUTH_REFRESH_RATE_LIMIT=2)
    def test_refresh_and_auth_throttles_are_isolated(self):
        anon = APIClient()
        self.assertEqual(anon.post('/api/v1/auth/refresh', {'refreshToken': 'bad-1'}, format='json').status_code, 401)
        self.assertEqual(anon.post('/api/v1/auth/refresh', {'refreshToken': 'bad-2'}, format='json').status_code, 401)
        self.assertEqual(anon.post('/api/v1/auth/refresh', {'refreshToken': 'bad-3'}, format='json').status_code, 429)

        login_ok = anon.post(
            '/api/v1/auth/login',
            {'login': 'student', 'password': 'Strong-Pass-2026!'},
            format='json',
        )
        self.assertEqual(login_ok.status_code, 200)
        fresh_refresh = login_ok.json()['refreshToken']

        # Exhaust account-level AuthThrottle on student login
        self.assertEqual(
            anon.post('/api/v1/auth/login', {'login': 'student', 'password': 'Wrong-Pass!'}, format='json').status_code,
            429,
        )
        # RefreshAuthThrottle on another IP still succeeds
        refreshed = anon.post(
            '/api/v1/auth/refresh',
            {'refreshToken': fresh_refresh},
            format='json',
            REMOTE_ADDR='198.51.100.77',
        )
        self.assertEqual(refreshed.status_code, 200)

    def test_latest_accepted_dedup_scores_coins_and_duplicate_submission_409(self):
        task = Task.objects.create(
            title='T1',
            description='desc',
            topic='Python',
            group_number='js-01',
            month=1,
            has_score=True,
            max_score=50,
        )
        Submission.objects.create(
            user=self.student,
            task=task,
            version=1,
            solution_link='https://github.com/u/r1',
            status=SubmissionStatusChoices.ACCEPTED,
            score=20,
        )
        Submission.objects.create(
            user=self.student,
            task=task,
            version=2,
            solution_link='https://github.com/u/r2',
            status=SubmissionStatusChoices.ACCEPTED,
            score=45,
        )

        ach_pts = (
            UserAchievement.objects.filter(user=self.student).aggregate(s=Sum('achievement__points'))['s'] or 0
        )
        me = self.student_client.get('/api/v1/users/me').json()
        self.assertEqual(me['stats']['totalScore'], 45)
        self.assertEqual(me['totalEarnedPoints'], 45 + ach_pts)

        balance = self.student_client.get('/api/v1/shop/balance').json()
        self.assertEqual(balance['availableCoins'], 45 + ach_pts)

        lb = self.student_client.get('/api/v1/leaderboard').json()['leaderboard']
        row = next(r for r in lb if r['id'] == self.student.id)
        self.assertEqual((row['totalScore'], row['tasksAcceptedCount']), (45, 1))

        admin_users = self.mentor_client.get('/api/v1/admin/users').json()['users']
        admin_row = next(r for r in admin_users if r['id'] == self.student.id)
        self.assertEqual((admin_row['totalScore'], admin_row['tasksAcceptedCount']), (45, 1))

        dup = self.student_client.post(
            '/api/v1/submissions',
            {'taskId': task.id, 'solutionLink': 'https://github.com/u/r3'},
            format='json',
        )
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(Submission.objects.filter(user=self.student, task=task).count(), 2)

    def test_submission_review_state_machine_required_score_and_optimistic_lock(self):
        scored_task = Task.objects.create(
            title='Scored',
            description='desc',
            topic='Python',
            group_number='js-01',
            month=1,
            has_score=True,
            max_score=50,
        )
        sub = Submission.objects.create(
            user=self.student,
            task=scored_task,
            version=1,
            solution_link='https://github.com/u/r1',
            status=SubmissionStatusChoices.SENT,
        )

        no_score = self.mentor_client.patch(
            f'/api/v1/submissions/{sub.id}',
            {'status': 'ACCEPTED'},
            format='json',
        )
        self.assertEqual(no_score.status_code, 400)

        stale_ts = (sub.updated_at - timedelta(seconds=10)).isoformat()
        stale = self.mentor_client.patch(
            f'/api/v1/submissions/{sub.id}',
            {'status': 'ACCEPTED', 'score': 40, 'expectedUpdatedAt': stale_ts},
            format='json',
        )
        self.assertEqual(stale.status_code, 409)

        ok = self.mentor_client.patch(
            f'/api/v1/submissions/{sub.id}',
            {'status': 'ACCEPTED', 'score': 40, 'expectedUpdatedAt': sub.updated_at.isoformat()},
            format='json',
        )
        self.assertEqual(ok.status_code, 200)

        for target in ('SENT', 'IN_REVIEW'):
            bad_trans = self.mentor_client.patch(
                f'/api/v1/submissions/{sub.id}',
                {'status': target},
                format='json',
            )
            self.assertEqual(bad_trans.status_code, 400)

        rev = self.mentor_client.patch(
            f'/api/v1/submissions/{sub.id}',
            {'status': 'REVISION'},
            format='json',
        )
        self.assertEqual(rev.status_code, 200)

        unscored_task = Task.objects.create(
            title='Unscored',
            description='desc',
            topic='Python',
            group_number='js-01',
            month=1,
            has_score=False,
            max_score=None,
        )
        unscored_sub = Submission.objects.create(
            user=self.student,
            task=unscored_task,
            version=1,
            solution_link='https://github.com/u/r2',
            status=SubmissionStatusChoices.SENT,
        )
        self.assertEqual(
            self.mentor_client.patch(
                f'/api/v1/submissions/{unscored_sub.id}',
                {'status': 'ACCEPTED'},
                format='json',
            ).status_code,
            200,
        )

        admin_sub = Submission.objects.create(
            user=self.student,
            task=scored_task,
            version=2,
            solution_link='https://github.com/u/r3',
            status=SubmissionStatusChoices.SENT,
        )
        sub_admin = SubmissionAdmin(Submission, admin.site)
        sub_admin.message_user = MagicMock()
        sub_admin.mark_accepted(_superuser_request(), Submission.objects.filter(pk=admin_sub.pk))
        admin_sub.refresh_from_db()
        self.assertEqual(admin_sub.status, SubmissionStatusChoices.ACCEPTED)
        self.assertEqual(admin_sub.score, 50)

        admin_sub2 = Submission(
            user=self.student,
            task=scored_task,
            version=3,
            solution_link='https://github.com/u/r4',
            status=SubmissionStatusChoices.ACCEPTED,
            score=None,
        )
        sub_admin.save_model(_superuser_request(), admin_sub2, form=MagicMock(), change=False)
        admin_sub2.refresh_from_db()
        self.assertEqual(admin_sub2.score, 50)

    def test_streak_update_and_streak_days_achievement_on_submission_and_refresh(self):
        ach = Achievement.objects.create(
            code='TEST_STREAK_2',
            title='2 days streak',
            description='desc',
            trigger_type=TriggerTypeChoices.STREAK_DAYS,
            threshold=2,
            points=15,
            is_active=True,
        )
        task = Task.objects.create(
            title='Streak Task',
            description='desc',
            topic='Python',
            group_number='js-01',
            month=1,
        )
        self.student.streak_count = 1
        self.student.last_active_date = timezone.now() - timedelta(days=1)
        self.student.save()

        with patch('admin_panel.views.curriculum_views.validate_github_repository', return_value={'valid': True}):
            sub_resp = self.student_client.post(
                '/api/v1/submissions',
                {'taskId': task.id, 'solutionLink': 'https://github.com/u/streak'},
                format='json',
            )
        self.assertEqual(sub_resp.status_code, 201)
        self.student.refresh_from_db()
        self.assertEqual(self.student.streak_count, 2)
        self.assertTrue(UserAchievement.objects.filter(user=self.student, achievement=ach).exists())

        self.student.last_active_date = timezone.now() - timedelta(days=1)
        self.student.save(update_fields=['last_active_date'])
        r1 = APIClient().post('/api/v1/auth/refresh', {'refreshToken': self.student_refresh}, format='json')
        self.assertEqual(r1.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.streak_count, 3)

        self.student.last_active_date = timezone.now() - timedelta(days=3)
        self.student.save(update_fields=['last_active_date'])
        r2 = APIClient().post('/api/v1/auth/refresh', {'refreshToken': r1.json()['refreshToken']}, format='json')
        self.assertEqual(r2.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.streak_count, 1)

    def test_system_config_filters_sensitive_keys_omits_auto_create_groups_and_survives_cache_error(self):
        PlatformSetting.objects.create(key='custom_secret_key', value='topsecret', is_public=True)
        PlatformSetting.objects.create(key='custom_public_label', value='hello', is_public=True)
        invalidate_settings_cache()

        resp = APIClient().get('/api/v1/system/config')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn('custom_secret_key', body['settings'])
        self.assertEqual(body['settings'].get('custom_public_label'), 'hello')
        self.assertNotIn('allowAutoCreateGroups', body['features'])

        err = OperationalError('no such table: django_cache')
        with (
            patch('admin_panel.services.settings_service.cache.get', side_effect=err),
            patch('admin_panel.services.settings_service.cache.set', side_effect=err),
        ):
            fallback_resp = APIClient().get('/api/v1/system/config')
            self.assertEqual(fallback_resp.status_code, 200)

    def test_task_and_achievement_delete_protection_api_and_admin(self):
        task_with_sub = Task.objects.create(title='Busy', description='d', topic='Py', group_number='js-01', month=1)
        task_free = Task.objects.create(title='Free', description='d', topic='Py', group_number='js-01', month=1)
        Submission.objects.create(
            user=self.student, task=task_with_sub, version=1, solution_link='https://github.com/u/r1'
        )

        self.assertEqual(self.mentor_client.delete(f'/api/v1/tasks/{uuid4()}').status_code, 404)
        self.assertEqual(self.mentor_client.delete(f'/api/v1/tasks/{task_with_sub.id}').status_code, 409)
        self.assertTrue(Task.objects.filter(pk=task_with_sub.id).exists())
        self.assertEqual(self.mentor_client.delete(f'/api/v1/tasks/{task_free.id}').status_code, 200)
        self.assertFalse(Task.objects.filter(pk=task_free.id).exists())

        task_free2 = Task.objects.create(title='Free2', description='d', topic='Py', group_number='js-01', month=1)
        task_admin = TaskAdmin(Task, admin.site)
        task_admin.message_user = MagicMock()
        req = _superuser_request()
        self.assertFalse(task_admin.has_delete_permission(req, task_with_sub))
        self.assertTrue(task_admin.has_delete_permission(req, task_free2))
        task_admin.delete_model(req, task_with_sub)
        self.assertTrue(Task.objects.filter(pk=task_with_sub.id).exists())
        task_admin.delete_queryset(req, Task.objects.filter(pk__in=[task_with_sub.id, task_free2.id]))
        self.assertTrue(Task.objects.filter(pk=task_with_sub.id).exists())
        self.assertFalse(Task.objects.filter(pk=task_free2.id).exists())

        ach_awarded = Achievement.objects.create(code='AWARDED_1', title='Awarded', description='d')
        ach_unused = Achievement.objects.create(code='UNUSED_1', title='Unused', description='d')
        UserAchievement.objects.create(user=self.student, achievement=ach_awarded)

        ach_admin = AchievementAdmin(Achievement, admin.site)
        ach_admin.message_user = MagicMock()
        self.assertFalse(ach_admin.has_delete_permission(req, ach_awarded))
        self.assertTrue(ach_admin.has_delete_permission(req, ach_unused))
        ach_admin.delete_model(req, ach_awarded)
        self.assertTrue(Achievement.objects.filter(pk=ach_awarded.id).exists())
        ach_admin.delete_queryset(req, Achievement.objects.filter(pk__in=[ach_awarded.id, ach_unused.id]))
        self.assertTrue(Achievement.objects.filter(pk=ach_awarded.id).exists())
        self.assertFalse(Achievement.objects.filter(pk=ach_unused.id).exists())

    def test_no_n_plus_one_on_tasks_admin_users_leaderboard_and_study_group_admin(self):
        tasks = []
        for idx in range(2):
            t = Task.objects.create(title=f'T{idx}', description='d', topic='Py', group_number='js-01', month=1, order=idx)
            Submission.objects.create(user=self.student, task=t, version=1, solution_link='https://github.com/u/r')
            tasks.append(t)

        s2 = create_user(login='stud_extra_0', role=RoleChoices.STUDENT, has_subscription=True, group_number='js-01', current_month=1)
        Submission.objects.create(
            user=s2, task=tasks[0], version=1, solution_link='https://github.com/u/r', status=SubmissionStatusChoices.ACCEPTED, score=10
        )

        with CaptureQueriesContext(connection) as ctx_tasks_2:
            r_t2 = self.student_client.get('/api/v1/tasks')
        self.assertEqual(r_t2.status_code, 200)
        with CaptureQueriesContext(connection) as ctx_lb_2:
            r_lb2 = self.student_client.get('/api/v1/leaderboard')
        self.assertEqual(r_lb2.status_code, 200)
        with CaptureQueriesContext(connection) as ctx_au_2:
            r_au2 = self.mentor_client.get('/api/v1/admin/users')
        self.assertEqual(r_au2.status_code, 200)

        for idx in range(2, 10):
            t = Task.objects.create(title=f'T{idx}', description='d', topic='Py', group_number='js-01', month=1, order=idx)
            Submission.objects.create(user=self.student, task=t, version=1, solution_link='https://github.com/u/r')
            st = create_user(
                login=f'stud_extra_{idx}', role=RoleChoices.STUDENT, has_subscription=True, group_number='js-01', current_month=1
            )
            Submission.objects.create(
                user=st, task=t, version=1, solution_link='https://github.com/u/r', status=SubmissionStatusChoices.ACCEPTED, score=10
            )

        with CaptureQueriesContext(connection) as ctx_tasks_10:
            r_t10 = self.student_client.get('/api/v1/tasks')
        self.assertEqual(len(r_t10.json()['tasks']), 10)
        self.assertEqual(len(ctx_tasks_10), len(ctx_tasks_2))

        with CaptureQueriesContext(connection) as ctx_lb_10:
            r_lb10 = self.student_client.get('/api/v1/leaderboard')
        self.assertEqual(r_lb10.status_code, 200)
        self.assertEqual(len(ctx_lb_10), len(ctx_lb_2))

        with CaptureQueriesContext(connection) as ctx_au_10:
            r_au10 = self.mentor_client.get('/api/v1/admin/users')
        self.assertEqual(r_au10.status_code, 200)
        self.assertEqual(len(ctx_au_10), len(ctx_au_2))

        for idx in range(5):
            grp = StudyGroup.objects.create(name=f'py-0{idx}', month=1)
            Lesson.objects.create(title=f'L{idx}', video_link='https://youtu.be/dQw4w9WgXcQ', group_number=grp.name, month=1)
            Task.objects.create(title=f'TG{idx}', description='d', topic='Py', group_number=grp.name, month=1)

        sg_admin = StudyGroupAdmin(StudyGroup, admin.site)
        groups = list(sg_admin.get_queryset(_superuser_request()))
        self.assertGreaterEqual(len(groups), 5)
        with self.assertNumQueries(0):
            for grp in groups:
                sg_admin.students_count_badge(grp)
                sg_admin.lessons_count_badge(grp)
                sg_admin.tasks_count_badge(grp)

    def test_user_admin_group_selector_sync_and_recalculate_ranks(self):
        g2 = StudyGroup.objects.create(name='js-02', month=2)
        user_admin = UserAdmin(User, admin.site)
        user_admin.message_user = MagicMock()
        req = _superuser_request()

        form_set = MagicMock(changed_data=['group_selector'], cleaned_data={'group_selector': 'js-02'})
        user_admin.save_model(req, self.student, form_set, change=True)
        self.student.refresh_from_db()
        self.assertEqual(self.student.group_number, 'js-02')
        self.assertEqual(self.student.study_group_id, g2.id)

        form_clear = MagicMock(changed_data=['group_selector'], cleaned_data={'group_selector': ''})
        user_admin.save_model(req, self.student, form_clear, change=True)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.group_number)
        self.assertIsNone(self.student.study_group_id)

        s_high = create_user(login='stud_high', role=RoleChoices.STUDENT, has_subscription=True, group_number='js-01', current_month=1)
        s_mid = create_user(login='stud_mid', role=RoleChoices.STUDENT, has_subscription=True, group_number='js-01', current_month=1)
        s_low = create_user(login='stud_low', role=RoleChoices.STUDENT, has_subscription=True, group_number='js-01', current_month=1)

        t1 = Task.objects.create(title='Rank T1', description='d', topic='Py', group_number='js-01', month=1, max_score=100)
        Submission.objects.create(
            user=s_high, task=t1, version=1, solution_link='https://github.com/u/h', status=SubmissionStatusChoices.ACCEPTED, score=80
        )
        ScoreAdjustment.objects.create(user=s_high, admin=self.mentor, amount=10, reason='bonus', month=1)
        Submission.objects.create(
            user=s_mid, task=t1, version=1, solution_link='https://github.com/u/m', status=SubmissionStatusChoices.ACCEPTED, score=50
        )
        Submission.objects.create(
            user=s_low, task=t1, version=1, solution_link='https://github.com/u/l', status=SubmissionStatusChoices.ACCEPTED, score=10
        )
        MonthlyScoreArchive.objects.create(user=s_low, month=1, final_score=10, tasks_accepted_count=1, final_rank=1)

        user_admin.recalculate_student_scores(req, User.objects.filter(pk__in=[s_high.pk, s_mid.pk]))
        self.assertEqual(MonthlyScoreArchive.objects.get(user=s_high, month=1).final_rank, 1)
        self.assertEqual(MonthlyScoreArchive.objects.get(user=s_mid, month=1).final_rank, 2)
        self.assertEqual(MonthlyScoreArchive.objects.get(user=s_low, month=1).final_rank, 3)

    def test_media_asset_admin_defers_data_and_renders_lazy_url_preview(self):
        asset = MediaAsset.objects.create(
            kind='avatar',
            mime_type='image/webp',
            data=b'RIFFxxxxWEBP',
            size_bytes=12,
            owner_id=self.student.id,
        )
        ma_admin = MediaAssetAdmin(MediaAsset, admin.site)
        obj = ma_admin.get_queryset(_superuser_request()).get(pk=asset.pk)
        self.assertIn('data', obj.get_deferred_fields())
        with self.assertNumQueries(0):
            html = str(ma_admin.asset_preview(obj))
        self.assertIn(f'/api/v1/media/{asset.id}', html)
        self.assertIn('loading="lazy"', html)
        self.assertNotIn('base64', html)

    def test_profile_url_validation_and_admin_create_user_current_month_validation(self):
        for bad_url in (
            'javascript:alert(1)',
            '//evil.com/a.png',
            'relative/path.png',
            '/api/v1/media/1\\2',
            '/api/v1/media/1\n2',
        ):
            resp = self.student_client.patch('/api/v1/users/me', {'avatarUrl': bad_url}, format='json')
            self.assertEqual(resp.status_code, 400, bad_url)

        ok_resp = self.student_client.patch('/api/v1/users/me', {'avatarUrl': '  /api/v1/media/ok-id  '}, format='json')
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual(ok_resp.json()['user']['avatarUrl'], 'http://testserver/api/v1/media/ok-id')

        with override_settings(PLATFORM_OWNER_USER_ID=self.owner.id):
            for idx, bad_month in enumerate((True, 'abc', 0, 25)):
                resp = self.owner_client.post(
                    '/api/v1/admin/users',
                    {'login': f'badm_{idx}', 'password': 'Strong-Pass-2026!', 'currentMonth': bad_month},
                    format='json',
                )
                self.assertEqual(resp.status_code, 400, bad_month)

            empty_m = self.owner_client.post(
                '/api/v1/admin/users',
                {'login': 'emptym_user', 'password': 'Strong-Pass-2026!', 'currentMonth': ''},
                format='json',
            )
            self.assertEqual(empty_m.status_code, 201)
            self.assertEqual(empty_m.json()['currentMonth'], 1)

            valid_m = self.owner_client.post(
                '/api/v1/admin/users',
                {'login': 'validm_user', 'password': 'Strong-Pass-2026!', 'currentMonth': 6},
                format='json',
            )
            self.assertEqual(valid_m.status_code, 201)
            self.assertEqual(valid_m.json()['currentMonth'], 6)

        deep = 'x'
        for _ in range(18):
            deep = {'a': deep}
        deep_resp = APIClient().post('/api/v1/auth/login', deep, format='json')
        self.assertEqual(deep_resp.status_code, 400)


class AuditV2RegressionTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        invalidate_settings_cache()
        self.group = StudyGroup.objects.create(name='js-01', month=1, is_active=True)
        self.owner = create_user(login='v2_owner', role=RoleChoices.ADMIN, has_subscription=True, group_number='js-01')
        self.owner.set_password('Owner-Pass-2026!')
        self.owner.save()
        self.mentor = create_user(login='v2_mentor', role=RoleChoices.ADMIN, has_subscription=True, group_number='js-01')
        self.mentor.set_password('Mentor-Pass-2026!')
        self.mentor.save()
        self.student = create_user(
            login='v2_student',
            role=RoleChoices.STUDENT,
            has_subscription=True,
            group_number='js-01',
            current_month=1,
            avatar_url='/api/v1/media/presets/avatars/avatar-1.svg',
            banner_url='/api/v1/media/presets/banners/banner-1.svg',
        )
        self.student.set_password('Strong-Pass-2026!')
        self.student.save()

        self.owner_client = APIClient()
        owner_tok, _, _ = generate_tokens_for_user(self.owner)
        self.owner_client.credentials(HTTP_AUTHORIZATION='Bearer ' + owner_tok)

        self.mentor_client = APIClient()
        mentor_tok, _, _ = generate_tokens_for_user(self.mentor)
        self.mentor_client.credentials(HTTP_AUTHORIZATION='Bearer ' + mentor_tok)

        self.student_client = APIClient()
        stu_tok, _, _ = generate_tokens_for_user(self.student)
        self.student_client.credentials(HTTP_AUTHORIZATION='Bearer ' + stu_tok)

    def test_absolute_media_urls_svg_headers_and_system_config_host_isolation(self):
        ach = Achievement.objects.create(
            code='V2_ABS_ACH',
            title='Abs',
            icon_url='/api/v1/media/presets/icons/star.svg',
        )
        UserAchievement.objects.create(user=self.student, achievement=ach)

        me = self.student_client.get('/api/v1/users/me')
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['user']['avatarUrl'], 'http://testserver/api/v1/media/presets/avatars/avatar-1.svg')
        self.assertEqual(me.json()['user']['bannerUrl'], 'http://testserver/api/v1/media/presets/banners/banner-1.svg')

        lb = self.student_client.get('/api/v1/leaderboard')
        self.assertEqual(lb.status_code, 200)
        self.assertTrue(lb.json()['leaderboard'][0]['avatarUrl'].startswith('http://testserver/'))

        ach_detail = self.student_client.get(f'/api/v1/achievements/{ach.id}')
        self.assertEqual(ach_detail.status_code, 200)
        ach_json = ach_detail.json()['achievement']
        self.assertTrue(ach_json['iconUrl'].startswith('http://testserver/'))
        self.assertTrue(ach_json['recentAchievers'][0]['avatarUrl'].startswith('http://testserver/'))

        presets = self.student_client.get('/api/v1/media/presets')
        self.assertEqual(presets.status_code, 200)
        presets_json = presets.json()
        self.assertTrue(presets_json['avatars'][0]['url'].startswith('http://testserver/'))
        self.assertTrue(presets_json['banners'][0]['url'].startswith('http://testserver/'))
        self.assertTrue(presets_json['achievementIcons'][0]['url'].startswith('http://testserver/'))

        svg_resp = self.client.get('/api/v1/media/presets/icons/star.svg')
        self.assertEqual(svg_resp.status_code, 200)
        self.assertEqual(svg_resp['Cross-Origin-Resource-Policy'], 'cross-origin')
        self.assertIn("default-src 'none'", svg_resp['Content-Security-Policy'])

        with override_settings(ALLOWED_HOSTS=['api-a.example', 'api-b.example', 'testserver']):
            cfg_a = APIClient().get('/api/v1/system/config', HTTP_HOST='api-a.example').json()
            cfg_b = APIClient().get('/api/v1/system/config', HTTP_HOST='api-b.example').json()
            self.assertTrue(cfg_a['mediaPresets']['avatars'][0]['url'].startswith('http://api-a.example/'))
            self.assertTrue(cfg_b['mediaPresets']['avatars'][0]['url'].startswith('http://api-b.example/'))

    def test_admin_owner_permissions_forms_and_validation(self):
        from django.contrib.auth import get_user_model
        from django.core.exceptions import PermissionDenied
        from admin_panel.admin import LessonAdmin, LessonAdminForm, PlatformSettingAdmin, ShopOrderAdmin
        from admin_panel.models import ShopOrder, ShopProduct

        dj_model = get_user_model()
        dj_owner = dj_model.objects.create_superuser(username='v2-dj-owner', password='Owner-Password-2026!')
        dj_staff = dj_model.objects.create_user(username='v2-dj-staff', password='Staff-Password-2026!', is_staff=True)
        product = ShopProduct.objects.create(title='Item', price_som=100, price_coins=10, stock=1)
        ShopOrder.objects.create(user=self.student, product=product, price_coins=10)

        non_owner_req = RequestFactory().post('/admin/')
        non_owner_req.user = dj_staff
        owner_req = RequestFactory().get('/admin/')
        owner_req.user = dj_owner

        with override_settings(PLATFORM_OWNER_ADMIN_ID=str(dj_owner.pk)):
            self.client.force_login(dj_staff)
            self.assertEqual(self.client.get('/admin/admin_panel/user/').status_code, 403)
            self.assertEqual(self.client.get('/admin/admin_panel/platformsetting/').status_code, 403)

            with self.assertRaises(PermissionDenied):
                UserAdmin(User, admin.site).recalculate_student_scores(non_owner_req, User.objects.all())
            with self.assertRaises(PermissionDenied):
                StudyGroupAdmin(StudyGroup, admin.site).archive_groups(non_owner_req, StudyGroup.objects.all())
            with self.assertRaises(PermissionDenied):
                ShopOrderAdmin(ShopOrder, admin.site).cancel_orders(non_owner_req, ShopOrder.objects.all())
            with self.assertRaises(PermissionDenied):
                PlatformSettingAdmin(PlatformSetting, admin.site).seed_default_settings(
                    non_owner_req, PlatformSetting.objects.all()
                )
            self.assertFalse(MediaAssetAdmin(MediaAsset, admin.site).has_add_permission(owner_req))

        long_bad_url = 'https://example.com/' + 'x' * 160
        bad_lesson_form = LessonAdminForm(
            data={'title': 'L', 'group_number': 'ALL', 'month': 1, 'order': 1, 'video_link': long_bad_url}
        )
        self.assertFalse(bad_lesson_form.is_valid())
        lesson_admin = LessonAdmin(Lesson, admin.site)
        lesson = Lesson(title='L', month=1, video_link=long_bad_url)
        with patch.object(lesson_admin, 'message_user'):
            lesson_admin.save_model(owner_req, lesson, MagicMock(changed_data=[]), False)
        self.assertEqual(lesson.youtube_id, '')

        with self.assertRaises(ValidationError):
            validate_setting_value('some_int', True, 'int')

    def test_register_input_validation_submissions_and_easter_egg_alias(self):
        from datetime import datetime, timezone as dt_timezone

        group2 = StudyGroup.objects.create(name='js-02', month=3, is_active=True)
        anon = APIClient()

        reg_id = anon.post(
            '/api/v1/auth/register',
            {'login': 'reg_by_id', 'password': 'Strong-Pass-2026!', 'groupId': group2.id, 'currentMonth': 9},
            format='json',
        )
        self.assertEqual(reg_id.status_code, 201)
        self.assertEqual(
            (reg_id.json()['user']['groupId'], reg_id.json()['user']['groupNumber'], reg_id.json()['user']['currentMonth']),
            (group2.id, 'js-02', 3),
        )

        reg_ci = anon.post(
            '/api/v1/auth/register',
            {'login': 'reg_ci', 'password': 'Strong-Pass-2026!', 'groupNumber': 'JS-02', 'currentMonth': 12},
            format='json',
        )
        self.assertEqual(reg_ci.status_code, 201)
        self.assertEqual(
            (reg_ci.json()['user']['groupId'], reg_ci.json()['user']['groupNumber'], reg_ci.json()['user']['currentMonth']),
            (group2.id, 'js-02', 3),
        )

        with override_settings(PLATFORM_OWNER_USER_ID=self.owner.id):
            bad_json = self.owner_client.post('/api/v1/admin/users', data='[]', content_type='application/json')
            self.assertEqual(bad_json.status_code, 400)
            bad_role = self.owner_client.get('/api/v1/admin/users?role=INVALID')
            self.assertEqual(bad_role.status_code, 400)

        self.assertEqual(self.student_client.get('/api/v1/shop/orders/my?status=INVALID').status_code, 400)
        self.assertEqual(self.student_client.get('/api/v1/leaderboard?month=99999999999999999999').status_code, 400)
        self.assertEqual(self.student_client.get('/api/v1/leaderboard?page=99999999999999999999').status_code, 400)

        surrogate_login = anon.post('/api/v1/auth/login', data=b'{"login": "\\ud800", "password": "x"}', content_type='application/json')
        self.assertIn(surrogate_login.status_code, (400, 401))

        task = Task.objects.create(title='HW1', topic='Py', month=1, max_score=10)
        with patch('admin_panel.views.curriculum_views.validate_github_repository', return_value={'valid': True}):
            s1 = self.student_client.post('/api/v1/submissions', {'taskId': task.id, 'solutionLink': 'https://github.com/u/r1'}, format='json')
        self.assertEqual(s1.status_code, 201)
        sub_id = s1.json()['id']
        dup = self.student_client.post('/api/v1/submissions', {'taskId': task.id, 'solutionLink': 'https://github.com/u/r2'}, format='json')
        self.assertEqual(dup.status_code, 409)

        real_sub = Submission.objects.get(pk=sub_id)
        naive_dt = datetime(2026, 2, 1, 10, 0, 0)
        real_sub.updated_at = naive_dt
        with patch('admin_panel.views.curriculum_views.Submission.objects') as mock_mgr:
            mock_mgr.filter.return_value.values_list.return_value.first.return_value = self.student.id
            mock_mgr.select_for_update.return_value.select_related.return_value.get.return_value = real_sub
            stale = self.mentor_client.patch(
                f'/api/v1/submissions/{sub_id}',
                {'status': 'IN_REVIEW', 'expectedUpdatedAt': '2026-02-01T10:05:00Z'},
                format='json',
            )
            self.assertEqual(stale.status_code, 409)
            ok_patch = self.mentor_client.patch(
                f'/api/v1/submissions/{sub_id}',
                {'status': 'IN_REVIEW', 'expectedUpdatedAt': naive_dt.replace(tzinfo=dt_timezone.utc).isoformat()},
                format='json',
            )
            self.assertEqual(ok_patch.status_code, 200)

        egg = self.student_client.post('/api/v1/me/claim-easter-egg')
        self.assertEqual(egg.status_code, 200)
        self.assertTrue(egg.json()['success'])

    def test_shop_balance_ignores_streak_and_revision_in_place_gamification(self):
        from admin_panel.services.achievement_service import ensure_default_achievements
        from admin_panel.services.shop_service import shop_balance

        ensure_default_achievements()
        streaker = create_user(login='v2_streaker', role=RoleChoices.STUDENT, streak_count=20)
        self.assertEqual(shop_balance(streaker)['availableCoins'], 0)

        for idx in range(3):
            task = Task.objects.create(title=f'T{idx}', topic='Py', month=1, max_score=10)
            sub = Submission.objects.create(user=streaker, task=task, version=1, status=SubmissionStatusChoices.SENT)
            sub.status = SubmissionStatusChoices.REVISION
            sub.save()
            sub.status = SubmissionStatusChoices.ACCEPTED
            sub.score = 10
            sub.save()
            sub.refresh_from_db()
            self.assertTrue(sub.was_revised)

        self.assertTrue(UserAchievement.objects.filter(user=streaker, achievement__code='BUG_HUNTER').exists())
        self.assertFalse(UserAchievement.objects.filter(user=streaker, achievement__code='SPEED_DEMON').exists())

    def test_outbox_retry_rate_limit_truncation_polling_and_auth_code_ttl(self):
        from admin_panel.services.telegram_service import handle_start_command

        corrupt = TelegramOutbox.objects.create(chat_id='100', dedupe_key=str(uuid4()), payload={'encrypted': 'not-a-fernet-token'})
        self.assertFalse(outbox_service.deliver(corrupt.pk))
        corrupt.refresh_from_db()
        self.assertEqual(corrupt.status, 'failed')

        with self.settings(TELEGRAM_OUTBOX_EAGER=False):
            outbox_service.enqueue('100', 'Rate test', dedupe_key='rate-429-key')
        rate_item = TelegramOutbox.objects.get(dedupe_key='rate-429-key')
        with (
            patch('admin_panel.services.telegram_service.get_bot_token', return_value='tok'),
            patch('httpx.Client.post', return_value=_mock_httpx_response(429, {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 30}})),
        ):
            self.assertFalse(outbox_service.deliver(rate_item.pk))
        rate_item.refresh_from_db()
        self.assertEqual(rate_item.status, 'pending')
        self.assertEqual(rate_item.attempts, 0)
        self.assertGreater(rate_item.available_at, timezone.now() + timedelta(seconds=20))

        sending_item = TelegramOutbox.objects.create(chat_id='101', dedupe_key=str(uuid4()), payload={'encrypted': 'x'}, status='sending')
        failed_item = TelegramOutbox.objects.create(chat_id='102', dedupe_key=str(uuid4()), payload={'encrypted': 'x'}, status='failed', attempts=5)
        res = outbox_service.retry_outbox_queryset(TelegramOutbox.objects.filter(pk__in=[sending_item.pk, failed_item.pk]), drain_now=False)
        self.assertEqual(res['queued'], 1)
        sending_item.refresh_from_db()
        failed_item.refresh_from_db()
        self.assertEqual(sending_item.status, 'sending')
        self.assertEqual(failed_item.status, 'pending')

        with (
            patch('admin_panel.services.telegram_service.get_bot_token', return_value='tok'),
            patch('httpx.Client.post', return_value=_mock_httpx_response(200, {'ok': True})) as mock_post,
        ):
            self.assertTrue(send_telegram_message('123', '<b>' + 'a' * 5000 + '</b>'))
        self.assertLessEqual(len(mock_post.call_args.kwargs['json']['text']), 4096)

        poison_resp = _mock_httpx_response(200, {'ok': True, 'result': [{'update_id': 500, 'message': {'chat': {'id': 1}, 'text': '/help'}}]})
        empty_resp = _mock_httpx_response(200, {'ok': True, 'result': []})
        with (
            patch('admin_panel.services.telegram_service.get_bot_token', return_value='tok'),
            patch('admin_panel.services.telegram_service.process_telegram_update', side_effect=RuntimeError('boom')),
            patch('time.sleep'),
            patch('httpx.Client') as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = _mock_httpx_response(200, {'ok': True})
            mock_client.get.side_effect = [poison_resp, poison_resp, poison_resp, empty_resp]
            final_offset = run_telegram_polling(max_cycles=4)
        self.assertEqual(final_offset, 501)
        self.assertEqual(mock_client.get.call_args_list[3].kwargs['params']['offset'], 501)

        self.student.telegram_auth_code = 'expcode1'
        self.student.save(update_fields=['telegram_auth_code'])
        cache_set_safe('tg_auth_code_ttl:expcode1', {'user_id': self.student.id, 'exp': timezone.now().timestamp() - 10}, 60)
        reply = handle_start_command('9001', 'expcode1', 'v2user')
        self.assertIn('истёк', reply)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.telegram_auth_code)
