from unittest.mock import patch
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from admin_panel.views.auth_views import RegisterView
from admin_panel.services import telegram_service as tg


class DeliveryAndClosedRegistrationTests(SimpleTestCase):
    def test_public_registration_is_closed(self):
        response = RegisterView.as_view()(APIRequestFactory().post("/", {}))
        self.assertEqual(response.status_code, 403)



from django.test import TransactionTestCase, override_settings
from django.db import connection
from admin_panel.test_support import UNMANAGED_MODELS, create_schema, clear_data, subscribe
from admin_panel.models import User, StudyGroup, SubscriptionGrant
from admin_panel.services.subscription_service import grant_subscription, handle_subscription_start
from rest_framework.test import APIClient


@override_settings(TELEGRAM_OUTBOX_EAGER=True)
class SubscriptionIntegrationTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()

    @override_settings(TELEGRAM_WEBHOOK_SECRET='test-secret')
    def test_pending_subscription_claim_and_username_reuse(self):
        group = StudyGroup.objects.create(name='js-02', month=2)
        grant_subscription('@Student_test', group, None, 'owner')
        update = {'update_id': 1, 'message': {
            'chat': {'id': 12345, 'type': 'private'},
            'from': {'id': 12345, 'username': 'student_test'},
            'text': '/start',
        }}
        with patch.object(tg, 'send_telegram_message', return_value=True) as send:
            response = APIClient().post(
                '/api/v1/telegram/webhook', update, format='json',
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret',
            )
        self.assertEqual(response.status_code, 200)
        grant = SubscriptionGrant.objects.get(telegram_username='student_test')
        self.assertEqual(grant.user.current_month, 2)
        self.assertTrue(grant.user.has_subscription)
        self.assertTrue(grant.user.must_change_password)
        self.assertTrue(any('Временный пароль' in call.kwargs.get('text', '') for call in send.call_args_list))
        handle_subscription_start('99999', 'student_test')
        grant.refresh_from_db()
        self.assertEqual(grant.telegram_user_id, '12345')

    def test_started_bot_before_grant(self):
        handle_subscription_start('12345', 'student_test')
        group = StudyGroup.objects.create(name='js-02', month=2)
        with patch.object(tg, 'send_telegram_message', return_value=True):
            grant = grant_subscription('student_test', group, None, 'owner')
        self.assertIsNone(grant.user_id)
        with patch.object(tg, 'send_telegram_message', return_value=True):
            handle_subscription_start('12345', 'student_test')
        grant.refresh_from_db()
        self.assertIsNotNone(grant.user_id)

    def test_course_requires_subscription_and_password_change(self):
        user = User.objects.create(login='closed', password_hash='x')
        client = APIClient()
        client.force_authenticate(user)
        for path in ('lessons', 'tasks', 'submissions', 'achievements', 'leaderboard'):
            self.assertEqual(client.get('/api/v1/' + path).status_code, 403)
        subscribe(user)
        user.has_subscription = True
        user.save()
        self.assertEqual(client.get('/api/v1/tasks').status_code, 200)
        user.must_change_password = True
        user.save()
        self.assertEqual(client.get('/api/v1/tasks').status_code, 403)

    def test_webhook_rejects_forged_updates(self):
        self.assertEqual(APIClient().post('/api/v1/telegram/webhook', {}, format='json').status_code, 403)

    def test_nonowner_cannot_grant(self):
        client = APIClient()
        client.force_authenticate(User.objects.create(login='admin_other', role='ADMIN', password_hash='x'))
        self.assertEqual(client.post('/api/v1/admin/subscriptions/grant', {}, format='json').status_code, 403)


    def test_task_creation_targets_group_and_month_after_commit(self):
        from admin_panel.models import Task
        from django.db import transaction
        users = [('a', 'js-01', 1, '10'), ('b', 'py-01', 1, '20'), ('c', 'js-02', 2, '30')]
        for login, group, month, chat in users:
            User.objects.create(login=login, password_hash='x', group_number=group, current_month=month, telegram_chat_id=chat)
        with patch.object(tg, 'send_telegram_message', return_value=True) as send:
            with transaction.atomic():
                Task.objects.create(title='Target', topic='x', month=1, group_number='js-01')
                self.assertFalse(send.called)
            self.assertEqual([c.args[0] for c in send.call_args_list], ['10'])
            send.reset_mock()
            Task.objects.create(title='All', topic='x', month=1, group_number=None)
            self.assertEqual({c.args[0] for c in send.call_args_list}, {'10', '20'})


    @override_settings(PLATFORM_OWNER_ADMIN_ID='1')
    def test_owner_can_grant_using_admin_session(self):
        from django.contrib.auth import get_user_model
        owner = get_user_model().objects.create_superuser(pk=1, username='owner', password='test-owner-password')
        group = StudyGroup.objects.create(name='js-01')
        client = APIClient()
        client.force_login(owner)
        response = client.post('/api/v1/admin/subscriptions/grant', {'telegram_username': '@new_student', 'group_id': group.pk}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['activated'])

    def test_reset_token_is_single_use(self):
        from admin_panel.services.subscription_service import recovery_link
        user = User.objects.create(login='reset', password_hash='old')
        token = recovery_link(user).split('reset=')[1]
        client = APIClient()
        payload = {'token': token, 'new_password': 'new-password-123'}
        self.assertEqual(client.post('/api/v1/auth/reset-password', payload, format='json').status_code, 200)
        self.assertEqual(client.post('/api/v1/auth/reset-password', payload, format='json').status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password('new-password-123'))


    def test_broadcast_returns_actual_delivery_counts(self):
        with patch.object(tg, 'send_telegram_message', side_effect=[True, False]):
            result = tg.async_broadcast_message(['10', '20', '10'], 'test')
        self.assertEqual(result, {'sent': 1, 'errors': 1, 'queued': 1})
