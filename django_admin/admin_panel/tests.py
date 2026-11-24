from django.utils import timezone
import io
import json
from PIL import Image
from django.test import TransactionTestCase, Client, override_settings
from django.db import connection
from admin_panel.models import (
    User,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    Achievement,
    UserAchievement,
    MediaAsset,
    Session,
    StudyGroup,
    SubscriptionGrant, TelegramIdentity, PasswordResetTicket,
    RoleChoices,
    SubmissionStatusChoices,
)
from admin_panel.services.achievement_service import ensure_default_achievements

from admin_panel.test_support import UNMANAGED_MODELS, create_user, create_schema, clear_data, subscribe


class MertsPlatformFullAPITestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        self.client = Client()
        ensure_default_achievements()

    def test_01_system_config(self):
        resp = self.client.get('/api/v1/system/config')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['platform']['name'], 'MertsPlatform')
        self.assertIn('STUDENT', data['roles'])
        self.assertIn('banners', data['mediaPresets'])

    def test_02_health_check(self):
        resp = self.client.get('/api/v1/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['database'], 'up')

        resp_shallow = self.client.get('/api/v1/health?shallow=true')
        self.assertEqual(resp_shallow.status_code, 200)
        self.assertEqual(resp_shallow.json()['mode'], 'shallow')

    def test_03_auth_flow_and_on_register_achievement(self):
        # Empty payload returns 400; valid registration creates student without subscription (has_subscription=False).
        bad_resp = self.client.post('/api/v1/auth/register', data={}, content_type='application/json')
        self.assertEqual(bad_resp.status_code, 400)

        reg_payload = {
            "login": "test_student",
            "password": "Password123!",
            "groupNumber": "GRP-101",
            "name": "Иван Студентов",
        }
        reg_resp = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps(reg_payload),
            content_type='application/json',
        )
        self.assertEqual(reg_resp.status_code, 201)
        reg_data = reg_resp.json()
        self.assertIn('accessToken', reg_data)
        self.assertTrue(reg_data['user']['has_subscription'])
        user = User.objects.get(pk=reg_data['user']['id'])
        self.assertTrue(user.has_subscription)
        self.assertEqual(UserAchievement.objects.filter(user=user, achievement__code='WELCOME').count(), 1)

        dup_resp = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps(reg_payload),
            content_type='application/json',
        )
        self.assertEqual(dup_resp.status_code, 409)

        # 2. Login with valid credentials
        login_payload = {
            "login": "test_student",
            "password": "Password123!",
        }
        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps(login_payload),
            content_type='application/json'
        )
        self.assertEqual(login_resp.status_code, 200)
        login_data = login_resp.json()
        token = login_data['accessToken']
        self.assertTrue(bool(token))

        auth_hdr = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        for path in ('/api/v1/lessons', '/api/v1/tasks', '/api/v1/achievements'):
            self.assertEqual(self.client.get(path, **auth_hdr).status_code, 200, path)

        # 3. Refresh token
        refresh_token = login_data['refreshToken']
        refresh_resp = self.client.post(
            '/api/v1/auth/refresh',
            data=json.dumps({"refreshToken": refresh_token}),
            content_type='application/json'
        )
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertIn('accessToken', refresh_resp.json())

    def test_03b_register_and_serializer_name_fallback_to_login(self):
        from admin_panel.authentication import generate_tokens_for_user
        from admin_panel.serializers import ShortUserSerializer, UserProfileSerializer

        # 3-field registration without name falls back to stripped login
        resp_no_name = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps({
                'login': '  student_3field  ',
                'password': 'Password123!',
                'groupNumber': 'GRP-101',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_no_name.status_code, 201)
        self.assertEqual(resp_no_name.json()['user']['name'], 'student_3field')
        self.assertEqual(User.objects.get(login='student_3field').name, 'student_3field')

        # Registration with whitespace-only name falls back to stripped login
        resp_blank_name = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps({
                'login': '  student_blank  ',
                'password': 'Password123!',
                'groupNumber': 'GRP-101',
                'name': '   ',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp_blank_name.status_code, 201)
        self.assertEqual(resp_blank_name.json()['user']['name'], 'student_blank')
        self.assertEqual(User.objects.get(login='student_blank').name, 'student_blank')

        # Legacy users with name=None or whitespace still serialize with login; padded names get stripped
        legacy_null = create_user(login='legacy_null', name=None, group_number='GRP-101')
        legacy_blank = create_user(login='legacy_blank', name='   ', group_number='GRP-101')
        named_user = create_user(login='named_user', name='  Иван  ', group_number='GRP-101')

        for serializer_cls in (UserProfileSerializer, ShortUserSerializer):
            self.assertEqual(serializer_cls(legacy_null).data['name'], 'legacy_null')
            self.assertEqual(serializer_cls(legacy_blank).data['name'], 'legacy_blank')
            self.assertEqual(serializer_cls(named_user).data['name'], 'Иван')

        access_token, _, _ = generate_tokens_for_user(legacy_null)
        me_resp = self.client.get('/api/v1/users/me', HTTP_AUTHORIZATION=f'Bearer {access_token}')
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()['user']['name'], 'legacy_null')

    def test_04_user_profile_and_password_update(self):
        # Create user
        user = create_user(has_subscription=True,
            login='student_profile',
            role=RoleChoices.STUDENT,
            name='Петр',
            group_number='GRP-102',
            streak_count=5,
            last_active_date=timezone.now(),
        )
        user.set_password('SecretPass123')
        user.save()

        # Login to get JWT
        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "student_profile", "password": "SecretPass123"}),
            content_type='application/json'
        )
        token = login_resp.json()['accessToken']
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        # GET /users/me
        me_resp = self.client.get('/api/v1/users/me', **auth_header)
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        self.assertEqual(me_data['user']['name'], 'Петр')
        self.assertEqual(me_data['stats']['streakCount'], 5)

        # PATCH /users/me
        patch_resp = self.client.patch(
            '/api/v1/users/me',
            data=json.dumps({"name": "Петр Великий", "telegram": "@petr"}),
            content_type='application/json',
            **auth_header
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()['user']['name'], 'Петр Великий')

        # PUT /users/me/password
        pw_resp = self.client.put(
            '/api/v1/users/me/password',
            data=json.dumps({"currentPassword": "SecretPass123", "newPassword": "NewSecretPass456"}),
            content_type='application/json',
            **auth_header
        )
        self.assertEqual(pw_resp.status_code, 200)

        # Verify login with new password
        login2_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "student_profile", "password": "NewSecretPass456"}),
            content_type='application/json'
        )
        self.assertEqual(login2_resp.status_code, 200)

    def test_05_media_persistence_and_webp_optimization(self):
        # Create student and mentor
        user = create_user(has_subscription=True, login='student_media', role=RoleChoices.STUDENT)
        user.set_password('Pass1234!')
        user.save()

        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "student_media", "password": "Pass1234!"}),
            content_type='application/json'
        )
        token = login_resp.json()['accessToken']
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        # Create sample PNG in memory
        img = Image.new('RGB', (800, 800), color=(255, 128, 0))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        img_bytes.name = 'avatar.png'

        # Upload avatar
        upload_resp = self.client.post(
            '/api/v1/users/me/avatar',
            data={'avatar': img_bytes},
            **auth_header
        )
        self.assertEqual(upload_resp.status_code, 200)
        avatar_url = upload_resp.json()['avatarUrl']
        self.assertTrue(avatar_url.startswith('http://testserver/api/v1/media/'))

        # Fetch binary from GET /api/v1/media/<id>
        media_id = avatar_url.split('/')[-1]
        get_media_resp = self.client.get(f'/api/v1/media/{media_id}')
        self.assertEqual(get_media_resp.status_code, 200)
        self.assertEqual(get_media_resp['Content-Type'], 'image/webp')

        # Verify image dimensions in Pillow (must be cropped to 256x256 WebP)
        saved_img = Image.open(io.BytesIO(get_media_resp.content))
        self.assertEqual(saved_img.format, 'WEBP')
        self.assertEqual(saved_img.size, (256, 256))

        # Upload a second avatar to verify previous asset cleanup
        img_bytes2 = io.BytesIO()
        img.save(img_bytes2, format='PNG')
        img_bytes2.seek(0)
        img_bytes2.name = 'avatar2.png'

        upload_resp2 = self.client.post(
            '/api/v1/users/me/avatar',
            data={'avatar': img_bytes2},
            **auth_header
        )
        self.assertEqual(upload_resp2.status_code, 200)
        self.assertEqual(MediaAsset.objects.filter(owner_id=user.id, kind='AVATAR').count(), 1)

    def test_06_curriculum_submissions_and_dynamic_gamification(self):
        # 1. Create mentor and student
        mentor = create_user(has_subscription=True, login='mentor_test', role=RoleChoices.ADMIN)
        mentor.set_password('MentorPass123')
        mentor.save()

        student = create_user(has_subscription=True, login='student_hw', role=RoleChoices.STUDENT, group_number='GRP-1')
        student.set_password('StudentPass123')
        student.save()

        # Mentor token
        m_login = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "mentor_test", "password": "MentorPass123"}),
            content_type='application/json'
        )
        mentor_token = m_login.json()['accessToken']
        mentor_auth = {'HTTP_AUTHORIZATION': f'Bearer {mentor_token}'}

        # Student token
        s_login = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "student_hw", "password": "StudentPass123"}),
            content_type='application/json'
        )
        student_token = s_login.json()['accessToken']
        student_auth = {'HTTP_AUTHORIZATION': f'Bearer {student_token}'}

        # 2. Mentor creates task
        task_resp = self.client.post(
            '/api/v1/tasks',
            data=json.dumps({
                "title": "Практика Django REST",
                "description": "Сделать миграцию и тесты",
                "topic": "Backend",
                "month": 1,
                "order": 1,
                "hasScore": True,
                "maxScore": 20,
            }),
            content_type='application/json',
            **mentor_auth
        )
        self.assertEqual(task_resp.status_code, 201)
        task_id = task_resp.json()['id']

        # 3. Student submits solution
        sub_resp = self.client.post(
            '/api/v1/submissions',
            data=json.dumps({
                "taskId": task_id,
                "solutionLink": "https://github.com/student/hw-1",
                "comment": "Готово к проверке",
            }),
            content_type='application/json',
            **student_auth
        )
        self.assertEqual(sub_resp.status_code, 201)
        submission_id = sub_resp.json()['id']

        # 4. Mentor reviews submission with ACCEPTED and 20 points
        review_resp = self.client.patch(
            f'/api/v1/submissions/{submission_id}',
            data=json.dumps({
                "status": "ACCEPTED",
                "score": 20,
                "reviewerComment": "Отличная работа, принято!",
            }),
            content_type='application/json',
            **mentor_auth
        )
        self.assertEqual(review_resp.status_code, 200)

        # 5. Verify dynamic signals evaluated achievements:
        # Should award FIRST_STEP (ACCEPTED_TASKS) and SCORE_20 (TOTAL_SCORE >= 20) and PERFECT_SCORE
        user_ach_codes = list(UserAchievement.objects.filter(user_id=student.id).values_list('achievement__code', flat=True))
        self.assertIn('FIRST_STEP', user_ach_codes)
        self.assertIn('SCORE_20', user_ach_codes)
        self.assertIn('PERFECT_SCORE', user_ach_codes)

        # 6. Check student total score in me
        me_resp = self.client.get('/api/v1/users/me', **student_auth)
        self.assertEqual(me_resp.json()['stats']['totalScore'], 20)
        self.assertEqual(me_resp.json()['stats']['tasksAcceptedCount'], 1)

    def test_07_leaderboard_ranking(self):
        s1 = create_user(has_subscription=True, login='stud1', role=RoleChoices.STUDENT, current_month=1)
        s2 = create_user(has_subscription=True, login='stud2', role=RoleChoices.STUDENT, current_month=1)
        s1.set_password('Pass123!')
        s2.set_password('Pass123!')
        s1.save()
        s2.save()

        # Score adjustments: stud2 has 30, stud1 has 10
        admin = create_user(has_subscription=True, login='admin_adj', role=RoleChoices.ADMIN)
        ScoreAdjustment.objects.create(user=s2, admin=admin, amount=30, reason='Bonus', month=1)
        ScoreAdjustment.objects.create(user=s1, admin=admin, amount=10, reason='Bonus', month=1)

        # Login as s1
        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "stud1", "password": "Pass123!"}),
            content_type='application/json'
        )
        token = login_resp.json()['accessToken']
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        lb_resp = self.client.get('/api/v1/leaderboard?month=1', **auth_header)
        self.assertEqual(lb_resp.status_code, 200)
        board = lb_resp.json()['leaderboard']
        # Top 1 should be stud2 with 30 points
        self.assertEqual(board[0]['login'], 'stud2')
        self.assertEqual(board[0]['rank'], 1)
        self.assertEqual(board[0]['totalScore'], 30)

    def test_08_telegram_connect_and_disconnect(self):
        user = create_user(has_subscription=True, login='tg_user', role=RoleChoices.STUDENT)
        user.set_password('Pass123!')
        user.save()

        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({"login": "tg_user", "password": "Pass123!"}),
            content_type='application/json'
        )
        token = login_resp.json()['accessToken']
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        # Connect
        conn_resp = self.client.post('/api/v1/users/me/telegram/connect', **auth_header)
        self.assertEqual(conn_resp.status_code, 200)
        self.assertIn('link', conn_resp.json())
        self.assertTrue(conn_resp.json()['link'].startswith('https://t.me/'))

        # Disconnect
        disc_resp = self.client.delete('/api/v1/users/me/telegram/disconnect', **auth_header)
        self.assertEqual(disc_resp.status_code, 200)
        user.refresh_from_db()
        self.assertIsNone(user.telegram_chat_id)
        self.assertIsNone(user.telegram_auth_code)

    def test_09_achievement_admin_form_icon_handling(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from admin_panel.admin import AchievementAdminForm, AchievementAdmin
        from django.contrib.admin.sites import AdminSite

        # 1. Test preset icon selection
        form_data = {
            'code': 'PRESET_TEST',
            'title': 'Пресет тест',
            'category': 'general',
            'trigger_type': 'MANUAL',
            'points': 10,
            'description': 'Тестовое описание',
            'preset_selector': '/api/v1/media/presets/icons/sparkles.svg',
        }
        form = AchievementAdminForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['icon_url'], '/api/v1/media/presets/icons/sparkles.svg')

        # 2. Test custom file upload (PNG/SVG) to MediaAsset
        output = io.BytesIO()
        Image.new('RGB', (16, 16)).save(output, format='PNG')
        svg_content = output.getvalue()
        uploaded_file = SimpleUploadedFile(
            name="custom_badge.png",
            content=svg_content,
            content_type="image/png"
        )
        form_data2 = {
            'code': 'CUSTOM_UPLOAD_TEST',
            'title': 'Кастомная иконка',
            'category': 'SPECIAL',
            'trigger_type': 'MANUAL',
            'points': 25,
            'description': 'Тестовое описание',
        }
        form2 = AchievementAdminForm(data=form_data2, files={'custom_icon_file': uploaded_file})
        self.assertTrue(form2.is_valid(), form2.errors)
        self.assertEqual(MediaAsset.objects.filter(kind='ACHIEVEMENT_ICON').count(), 0)

        # Save via AchievementAdmin creates MediaAsset and sets icon_url
        from unittest.mock import MagicMock
        site = AdminSite()
        admin_obj = AchievementAdmin(Achievement, site)
        ach_instance = form2.save(commit=False)
        admin_obj.save_model(MagicMock(), ach_instance, form2, change=False)
        icon_url = ach_instance.icon_url
        self.assertTrue(icon_url.startswith('/api/v1/media/'))

        # Verify MediaAsset record in DB
        media_id = icon_url.split('/')[-1]
        asset = MediaAsset.objects.get(id=media_id)
        self.assertEqual(asset.kind, 'ACHIEVEMENT_ICON')
        self.assertEqual(asset.mime_type, 'image/webp')

        # 3. Test AchievementAdmin badges
        preview_html = admin_obj.icon_preview(ach_instance)
        self.assertIn(f'src="{icon_url}"', preview_html)
        badge_html = admin_obj.icon_source_badge(ach_instance)
        self.assertIn('Кастомный файл (PostgreSQL)', badge_html)

    def test_10_educational_notification_triggers_and_antispam(self):
        from unittest.mock import patch, MagicMock
        from django.contrib.admin.sites import AdminSite
        from admin_panel.admin import LessonAdmin, TaskAdmin
        from admin_panel.services.telegram_service import (
            notify_lesson_published,
            notify_task_published,
            notify_submission_reviewed,
            notify_achievement_unlocked,
            notify_score_adjustment_granted,
            notify_month_advanced,
        )

        # Create student and admin with telegram_chat_id
        admin_user = create_user(has_subscription=True,
            login='admin_notif',
            name='Админ Уведомлений',
            password_hash='hash123',
            role=RoleChoices.ADMIN,
            telegram_chat_id='111222333',
        )
        student = create_user(has_subscription=True,
            login='student_notif',
            name='Ученик Уведомлений',
            password_hash='hash123',
            role=RoleChoices.STUDENT,
            current_month=1,
            group_number='GRP-TG',
            telegram_chat_id='987654321',
        )

        # 1. Lesson Creation Trigger & Content
        with patch('admin_panel.services.telegram_service.async_broadcast_message') as mock_broadcast:
            lesson = Lesson.objects.create(
                title='Урок по Django Signals',
                group_number='GRP-TG',
                month=1,
                order=5,
                video_link='https://youtu.be/dQw4w9WgXcQ',
            )
            self.assertTrue(mock_broadcast.called)
            chat_ids, message = mock_broadcast.call_args[0]
            self.assertIn('987654321', chat_ids)
            self.assertIn('Урок по Django Signals', message)
            self.assertIn('lessons?month=1', message)

        # 2. Task Creation Trigger & Content
        with patch('admin_panel.services.telegram_service.async_broadcast_message') as mock_broadcast:
            task = Task.objects.create(
                title='ДЗ по Celery и Signals',
                topic='Signals',
                month=1,
                order=5,
                max_score=50,
                is_bonus=True,
            )
            self.assertTrue(mock_broadcast.called)
            chat_ids, message = mock_broadcast.call_args[0]
            self.assertIn('987654321', chat_ids)
            self.assertIn('ДЗ по Celery и Signals', message)
            self.assertIn('Бонусное задание', message)
            self.assertIn('tasks?month=1', message)

        # 3. Submission Creation (SENT) -> no review notification
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            submission = Submission.objects.create(
                user=student,
                task=task,
                solution_link='https://github.com/student/homework',
                status=SubmissionStatusChoices.SENT,
            )
            self.assertFalse(mock_send_single.called)

        # 3b. Submission Review (ACCEPTED with score and comment) -> notification triggered
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            submission.status = SubmissionStatusChoices.ACCEPTED
            submission.score = 50
            submission.reviewer_comment = 'Отличная работа!'
            submission.save()
            self.assertTrue(mock_send_single.called)
            target_user_id, message = mock_send_single.call_args[0]
            self.assertEqual(target_user_id, student.id)
            self.assertIn('Принято', message)
            self.assertIn('50 / 50', message)
            self.assertIn('Отличная работа!', message)

        # 3c. Anti-Spam Check: Save unchanged submission -> ZERO notifications
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            submission.save()
            self.assertFalse(mock_send_single.called)

        # 4. UserAchievement Trigger
        ach = Achievement.objects.create(
            code='MANUAL_NOTIFY_TEST',
            title='Ручная ачивка',
            trigger_type='MANUAL',
            points=10,
        )
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            UserAchievement.objects.create(
                user=student,
                achievement=ach,
            )
            self.assertTrue(mock_send_single.called)
            target_user_id, message = mock_send_single.call_args[0]
            self.assertEqual(target_user_id, student.id)
            self.assertIn('Получена новая ачивка!', message)
            self.assertIn(ach.title, message)

        # 5. ScoreAdjustment Trigger
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            ScoreAdjustment.objects.create(
                user=student,
                admin=admin_user,
                amount=15,
                reason='Активность в чате',
                month=1,
            )
            self.assertTrue(mock_send_single.called)
            target_user_id, message = mock_send_single.call_args[0]
            self.assertEqual(target_user_id, student.id)
            self.assertIn('Начислены бонусные баллы!', message)
            self.assertIn('+15 баллов', message)
            self.assertIn('Активность в чате', message)

        # 6. User Month Advancement:
        # 6a. Name change without month change -> no notification
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            student.name = 'Новое Имя'
            student.save()
            self.assertFalse(mock_send_single.called)

        # 6b. Month advancement: 1 -> 2 -> notification triggered
        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send_single:
            student.current_month = 2
            student.save()
            self.assertTrue(mock_send_single.called)
            target_user_id, message = mock_send_single.call_args[0]
            self.assertEqual(target_user_id, student.id)
            self.assertIn('Открыт новый этап обучения!', message)
            self.assertIn('Месяца 2', message)

        # 7. Unfold Admin Actions
        site = AdminSite()
        mock_request = MagicMock()
        mock_messages = []
        mock_request.user = admin_user

        lesson_admin = LessonAdmin(Lesson, site)
        lesson_admin.message_user = lambda req, msg, **kwargs: mock_messages.append(msg)
        with patch('admin_panel.services.telegram_service.async_broadcast_message', return_value={'sent': 1, 'errors': 0}):
            lesson_admin.broadcast_lesson_telegram(mock_request, Lesson.objects.filter(id=lesson.id))
        self.assertEqual(len(mock_messages), 1)
        self.assertIn('Доставлено в Telegram: 1. Бот не подключён:', mock_messages[0])

        task_admin = TaskAdmin(Task, site)
        task_admin.message_user = lambda req, msg, **kwargs: mock_messages.append(msg)
        with patch('admin_panel.services.telegram_service.async_broadcast_message', return_value={'sent': 1, 'errors': 0}):
            task_admin.broadcast_task_telegram(mock_request, Task.objects.filter(id=task.id))
        self.assertEqual(len(mock_messages), 2)
        self.assertIn('Доставлено в Telegram: 1. Бот не подключён:', mock_messages[1])

    def test_11_smart_groups_and_telegram_diagnostics(self):
        from unittest.mock import patch, MagicMock
        from django.contrib.admin.sites import AdminSite
        from admin_panel.services.group_service import (
            parse_month_from_group_name,
            ensure_study_groups_synced,
            get_study_group_choices,
        )
        from admin_panel.services.telegram_service import (
            send_test_telegram_message,
            notify_score_adjustment_granted,
            notify_task_published,
        )
        from admin_panel.admin import UserAdmin

        # 1. Test smart month parsing logic
        self.assertEqual(parse_month_from_group_name('js-02'), 2)
        self.assertEqual(parse_month_from_group_name('md-03'), 3)
        self.assertEqual(parse_month_from_group_name('py-01'), 1)
        self.assertEqual(parse_month_from_group_name('04'), 4)
        self.assertEqual(parse_month_from_group_name('frontend'), 1)
        self.assertEqual(parse_month_from_group_name(''), 1)
        self.assertEqual(parse_month_from_group_name(None), 1)

        # 2. Test auto-assignment of month during registration
        StudyGroup.objects.get_or_create(name="js-02", defaults={"month": 2})
        reg_payload = {
            "login": "student_group_test",
            "password": "Password123!",
            "groupNumber": "js-02",
            "name": "Студент Группы 2",
        }
        resp = self.client.post('/api/v1/auth/register', data=json.dumps(reg_payload), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        user_group = User.objects.get(login="student_group_test")
        self.assertEqual(user_group.current_month, 2)
        self.assertEqual(user_group.group_number, "js-02")
        self.assertIsNotNone(user_group.study_group)
        self.assertEqual(user_group.study_group.name, "js-02")

        # 3. Test StudyGroup counts and sync
        group = user_group.study_group
        self.assertGreaterEqual(group.students_count, 1)
        ensure_study_groups_synced()
        choices = get_study_group_choices(include_all=True)
        self.assertTrue(any('js-02' in c[0] for c in choices))

        # 4. Test Penalty / Fine notification (ScoreAdjustment amount < 0)
        admin_user = User.objects.filter(role=RoleChoices.ADMIN).first()
        if not admin_user:
            admin_user = create_user(has_subscription=True, login='admin_fine', password_hash='hash', role=RoleChoices.ADMIN)
        user_group.telegram_chat_id = "555666777"
        user_group.save()

        with patch('admin_panel.services.telegram_service.send_async_notification') as mock_send:
            ScoreAdjustment.objects.create(
                user=user_group,
                admin=admin_user,
                amount=-10,
                reason="Штраф за плагиат",
                month=2,
            )
            self.assertTrue(mock_send.called)
            target_id, msg = mock_send.call_args[0]
            self.assertEqual(target_id, user_group.id)
            self.assertIn('Начислен штраф!', msg)
            self.assertIn('Списано: <b>-10 баллов</b>', msg)
            self.assertIn('Штраф за плагиат', msg)

        # 5. Test send_test_telegram_message diagnostic
        user_no_tg = create_user(has_subscription=True, login='no_tg', password_hash='hash', role=RoleChoices.STUDENT)
        ok, report = send_test_telegram_message(user_no_tg)
        self.assertFalse(ok)
        self.assertIn('не заполнен Telegram Chat ID', report)

        with patch('httpx.Client.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {'ok': True}, headers={'content-type': 'application/json'})
            with patch('admin_panel.services.telegram_service.get_bot_token', return_value='dummy_token'):
                ok, report = send_test_telegram_message(user_group)
                self.assertTrue(ok)
                self.assertIn('успешно доставлено', report)

        # 6. Test UserAdmin test_telegram_connection action
        site = AdminSite()
        user_admin = UserAdmin(User, site)
        mock_req = MagicMock()
        mock_req.user.pk = 1
        mock_req.user.is_authenticated = True
        mock_req.user.is_superuser = True
        mock_msgs = []
        user_admin.message_user = lambda req, msg, level=None: mock_msgs.append((msg, level))
        with patch('httpx.Client.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {'ok': True}, headers={'content-type': 'application/json'})
            with patch('admin_panel.services.telegram_service.get_bot_token', return_value='dummy_token'):
                user_admin.test_telegram_connection(mock_req, User.objects.filter(id=user_group.id))
        self.assertEqual(len(mock_msgs), 1)
        self.assertIn('Успешно', mock_msgs[0][0])


class AdminSchemaRegressionTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        from django.contrib.auth import get_user_model
        self.owner = get_user_model().objects.create_superuser(username='schema-owner', password='Test-Owner-Password-2026!')
        self.client = Client()

    def test_login_and_groups_open(self):
        path = '/admin/admin_panel/studygroup/'
        self.assertEqual(self.client.get('/admin/login/?next=' + path).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 302)
        self.client.force_login(self.owner)
        StudyGroup.objects.create(name='js-01')
        self.assertEqual(self.client.get(path).status_code, 200)

    def test_missing_group_table_returns_503(self):
        from unittest.mock import patch
        from django.db import ProgrammingError
        self.client.force_login(self.owner)
        with patch('admin_panel.admin.StudyGroupAdmin.get_queryset', side_effect=ProgrammingError('no such table: StudyGroup')):
            self.assertEqual(self.client.get('/admin/admin_panel/studygroup/').status_code, 503)

    def test_admin_sections_search_and_group_filter(self):
        with override_settings(PLATFORM_OWNER_ADMIN_ID=str(self.owner.pk)):
            self._run_admin_sections_search_and_group_filter()

    def _run_admin_sections_search_and_group_filter(self):
        self.client.force_login(self.owner)
        group = StudyGroup.objects.create(name='audit-js')
        other_group = StudyGroup.objects.create(name='audit-py')
        mentor = create_user(login='mentor', role=RoleChoices.ADMIN)
        for current_group in (group, other_group):
            student = create_user(login=current_group.name, group_number=current_group.name)
            lesson = Lesson.objects.create(title='Аудит', group_number=current_group.name)
            task = Task.objects.create(title='Аудит', topic='Тема', group_number=current_group.name)
            submission = Submission.objects.create(user=student, task=task)
            adjustment = ScoreAdjustment.objects.create(user=student, admin=mentor, amount=1, reason='Аудит', month=1)
            if current_group == group:
                expected = {
                    'studygroup': (group, 'audit'),
                    'user': (student, 'audit'),
                    'lesson': (lesson, 'Аудит'),
                    'task': (task, 'Аудит'),
                    'submission': (submission, 'Аудит'),
                    'scoreadjustment': (adjustment, 'Аудит'),
                }
        for section, (record, query) in expected.items():
            with self.subTest(section=section):
                path = f'/admin/admin_panel/{section}/'
                response = self.client.get(path, {'q': query, 'study_group_name': group.name})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="study_group_name"')
                self.assertEqual(list(response.context['cl'].result_list), [record])
                self.assertEqual(list(self.client.get(path, {'q': 'no-match'}).context['cl'].result_list), [])

        achievement = Achievement.objects.create(code='ADMIN_AUDIT', title='Аудит')
        response = self.client.get('/admin/admin_panel/achievement/', {'q': achievement.code})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['cl'].result_list), [achievement])

    def test_admin_quick_edit_preserves_task_group(self):
        self.client.force_login(self.owner)
        group = StudyGroup.objects.create(name='audit-js', month=2)
        task = Task.objects.create(title='Аудит', topic='Тема', group_number=group.name, month=2)
        response = self.client.post('/admin/admin_panel/task/', {
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1',
            'form-0-id': task.pk, 'form-0-is_bonus': 'on', '_save': 'Сохранить',
        })
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertTrue(task.is_bonus)
        self.assertEqual((task.group_number, task.month), (group.name, 2))

    def test_missing_login_rate_table_fails_closed(self):
        from unittest.mock import patch
        from django.db import ProgrammingError
        with patch('admin_panel.throttles.consume_auth_attempt', side_effect=ProgrammingError('no such table: AuthRateBucket')):
            self.assertEqual(self.client.post('/admin/login/', {'username': 'owner', 'password': 'wrong'}).status_code, 503)

    def test_initializer_creates_missing_group_table_and_is_repeatable(self):
        from django.core.management import call_command
        with connection.schema_editor() as editor:
            editor.delete_model(StudyGroup)
        for _ in range(2):
            call_command('install_subscriptions', stdout=io.StringIO())
        self.assertEqual(StudyGroup.objects.count(), 0)

    def test_achievement_preset_icons_and_detail_endpoint(self):
        from admin_panel.services.achievement_service import DEFAULT_ACHIEVEMENTS_DATA

        ensure_default_achievements()

        # 1. All presets use full http(s)://.../api/v1/media/presets/icons/ and return 200 SVG
        presets_resp = self.client.get('/api/v1/media/presets')
        self.assertEqual(presets_resp.status_code, 200)
        preset_icons = presets_resp.json()['achievementIcons']
        self.assertEqual(len(preset_icons), 16)
        for item in preset_icons:
            self.assertRegex(item['url'], r'^https?://[^/]+/api/v1/media/presets/icons/[^/]+\.svg$', item)
            svg_resp = self.client.get(item['url'])
            self.assertEqual(svg_resp.status_code, 200, item['url'])
            self.assertIn('image/svg+xml', svg_resp['Content-Type'])

        for item in DEFAULT_ACHIEVEMENTS_DATA:
            self.assertTrue(item['icon_url'].startswith('/api/v1/media/presets/icons/'), item)
            svg_resp = self.client.get(item['icon_url'])
            self.assertEqual(svg_resp.status_code, 200, item['icon_url'])
            self.assertIn('image/svg+xml', svg_resp['Content-Type'])

        # 2. Detail endpoint GET /api/v1/achievements/<id>
        ach = Achievement.objects.get(code='SCORE_20')
        # Legacy DB path must be normalized by serializer
        Achievement.objects.filter(pk=ach.pk).update(icon_url='/api/v1/achievements/icons/star.svg')

        self.assertEqual(self.client.get(f'/api/v1/achievements/{ach.id}').status_code, 401)

        student = create_user(login='ach_detail_user', role=RoleChoices.STUDENT, has_subscription=True)
        student.set_password('Strong-Pass-2026!')
        student.save()
        UserAchievement.objects.create(user=student, achievement=ach)

        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({'login': 'ach_detail_user', 'password': 'Strong-Pass-2026!'}),
            content_type='application/json',
        )
        auth = {'HTTP_AUTHORIZATION': f"Bearer {login_resp.json()['accessToken']}"}

        self.assertEqual(self.client.get('/api/v1/achievements/nonexistent-id', **auth).status_code, 404)

        catalog_resp = self.client.get('/api/v1/achievements', **auth)
        self.assertEqual(catalog_resp.status_code, 200)
        catalog = catalog_resp.json()['achievements']
        self.assertTrue(catalog)
        for item in catalog:
            self.assertIn('isUnlocked', item)
            self.assertIn('isUnlockedByMe', item)
            self.assertEqual(item['isUnlockedByMe'], item['isUnlocked'])
            self.assertRegex(item['iconUrl'], r'^https?://[^/]+/api/v1/media/presets/icons/[^/]+\.svg$', item)

        unlocked_item = next(item for item in catalog if item['id'] == ach.id)
        self.assertEqual(unlocked_item['iconUrl'], 'http://testserver/api/v1/media/presets/icons/star.svg')
        self.assertTrue(unlocked_item['isUnlocked'])
        self.assertTrue(unlocked_item['isUnlockedByMe'])

        locked_item = next((item for item in catalog if not item['isUnlocked']), None)
        self.assertIsNotNone(locked_item)
        self.assertFalse(locked_item['isUnlocked'])
        self.assertFalse(locked_item['isUnlockedByMe'])

        detail_resp = self.client.get(f'/api/v1/achievements/{ach.id}', **auth)
        self.assertEqual(detail_resp.status_code, 200)
        payload = detail_resp.json()['achievement']
        self.assertEqual(payload['id'], ach.id)
        self.assertEqual(payload['iconUrl'], 'http://testserver/api/v1/media/presets/icons/star.svg')
        self.assertTrue(payload['isUnlocked'])
        self.assertTrue(payload['isUnlockedByMe'])
        self.assertEqual(payload['isUnlockedByMe'], payload['isUnlocked'])
        self.assertEqual(payload['unlockedCount'], 1)
        self.assertEqual(len(payload['recentAchievers']), 1)
        self.assertEqual(payload['recentAchievers'][0]['login'], 'ach_detail_user')

        locked_detail_resp = self.client.get(f"/api/v1/achievements/{locked_item['id']}", **auth)
        self.assertEqual(locked_detail_resp.status_code, 200)
        locked_payload = locked_detail_resp.json()['achievement']
        self.assertRegex(locked_payload['iconUrl'], r'^https?://[^/]+/api/v1/media/presets/icons/[^/]+\.svg$')
        self.assertFalse(locked_payload['isUnlocked'])
        self.assertFalse(locked_payload['isUnlockedByMe'])
        self.assertEqual(locked_payload['isUnlockedByMe'], locked_payload['isUnlocked'])

        me_ach_resp = self.client.get('/api/v1/users/me/achievements', **auth)
        self.assertEqual(me_ach_resp.status_code, 200)
        me_achievements = me_ach_resp.json()
        self.assertTrue(me_achievements)
        for entry in me_achievements:
            self.assertRegex(entry['achievement']['iconUrl'], r'^https?://[^/]+/api/v1/media/presets/icons/[^/]+\.svg$')
        me_star = next(entry for entry in me_achievements if entry['achievement']['id'] == ach.id)
        self.assertEqual(me_star['achievement']['iconUrl'], 'http://testserver/api/v1/media/presets/icons/star.svg')

        # 3. Fallback when request is not passed to serializer
        import os
        from unittest.mock import patch
        from admin_panel.serializers import AchievementSerializer

        with override_settings(BACKEND_PUBLIC_URL='https://api.example.com'):
            self.assertEqual(
                AchievementSerializer(ach).data['iconUrl'],
                'https://api.example.com/api/v1/media/presets/icons/star.svg',
            )
        with patch.dict(os.environ, {'BACKEND_PUBLIC_URL': '', 'SITE_URL': '', 'TRUST_HTTPS_PROXY': '1'}):
            self.assertEqual(
                AchievementSerializer(ach).data['iconUrl'],
                'https://166.0.28.165.sslip.io/api/v1/media/presets/icons/star.svg',
            )

    def test_dangling_study_group_does_not_break_login_or_profile(self):
        group = StudyGroup.objects.create(name='js-09', month=2)
        student = create_user(
            login='dangling_group_user',
            role=RoleChoices.STUDENT,
            group_number='js-09',
            study_group=group,
            has_subscription=True,
        )
        student.set_password('Strong-Pass-2026!')
        student.save()

        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({'login': 'dangling_group_user', 'password': 'Strong-Pass-2026!'}),
            content_type='application/json',
        )
        self.assertEqual(login_resp.status_code, 200)
        self.assertEqual(login_resp.json()['user']['groupId'], group.id)

        # Simulate a deleted StudyGroup leaving a dangling group_id in DB
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute('PRAGMA foreign_keys = OFF')
            try:
                cursor.execute('UPDATE "User" SET group_id = %s WHERE id = %s', ['deleted-group-id', student.id])
            finally:
                if connection.vendor == 'sqlite':
                    cursor.execute('PRAGMA foreign_keys = ON')

        relogin_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({'login': 'dangling_group_user', 'password': 'Strong-Pass-2026!'}),
            content_type='application/json',
        )
        self.assertEqual(relogin_resp.status_code, 200)
        self.assertIsNone(relogin_resp.json()['user']['groupId'])

        token = relogin_resp.json()['accessToken']
        me_resp = self.client.get('/api/v1/users/me', HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(me_resp.status_code, 200)
        self.assertIsNone(me_resp.json()['user']['groupId'])

    def test_avatar_and_banner_upload_return_fresh_user(self):
        student = create_user(login='media_user_payload', role=RoleChoices.STUDENT, has_subscription=True)
        student.set_password('Strong-Pass-2026!')
        student.save()

        login_resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({'login': 'media_user_payload', 'password': 'Strong-Pass-2026!'}),
            content_type='application/json',
        )
        auth = {'HTTP_AUTHORIZATION': f"Bearer {login_resp.json()['accessToken']}"}

        img = Image.new('RGB', (400, 400), color=(245, 158, 11))
        av_buf = io.BytesIO()
        img.save(av_buf, format='PNG')
        av_buf.seek(0)
        av_buf.name = 'avatar.png'

        av_resp = self.client.post('/api/v1/users/me/avatar', data={'avatar': av_buf}, **auth)
        self.assertEqual(av_resp.status_code, 200)
        av_json = av_resp.json()
        self.assertIn('user', av_json)
        self.assertEqual(av_json['user']['avatarUrl'], av_json['avatarUrl'])

        bn_buf = io.BytesIO()
        img.save(bn_buf, format='PNG')
        bn_buf.seek(0)
        bn_buf.name = 'banner.png'

        bn_resp = self.client.post('/api/v1/users/me/banner', data={'banner': bn_buf}, **auth)
        self.assertEqual(bn_resp.status_code, 200)
        bn_json = bn_resp.json()
        self.assertIn('user', bn_json)
        self.assertEqual(bn_json['user']['bannerUrl'], bn_json['bannerUrl'])


class BackendFlexibilityAndBugfixesTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        self.client = Client()
        from django.core.cache import cache
        cache.clear()
        from django.contrib.auth import get_user_model
        self.owner = get_user_model().objects.create_superuser(
            username='flex-owner', email='owner@example.com', password='Owner-Password-2026!'
        )

    def test_bug_032_lesson_admin_registration_and_widget(self):
        from django.contrib import admin
        from admin_panel.admin import GroupSavingAdmin, LessonAdmin, LessonAdminForm, SearchableGroupWidget
        self.assertIn(Lesson, admin.site._registry)
        registered = admin.site._registry[Lesson]
        self.assertIsInstance(registered, LessonAdmin)
        self.assertIsInstance(registered, GroupSavingAdmin)
        self.assertIs(registered.form, LessonAdminForm)
        self.assertIsInstance(registered.form.base_fields['group_number'].widget, SearchableGroupWidget)

    def test_bug_033_leaderboard_months_all_time_pagination_and_no_n_plus_1(self):
        from rest_framework.test import APIClient
        mentor = create_user(login='lb_mentor', role=RoleChoices.ADMIN)
        t1 = Task.objects.create(title='M1 Task', topic='Py', month=1, max_score=30)
        t2 = Task.objects.create(title='M2 Task', topic='Py', month=2, max_score=50)

        students = []
        for i in range(12):
            st = create_user(login=f'lb_stud_{i:02d}', name=f'Student {i:02d}', role=RoleChoices.STUDENT, current_month=2)
            students.append(st)
            # Month 1 scores: v1 overwritten by v2; studio_00 gets 10+i, etc.
            Submission.objects.create(user=st, task=t1, version=1, status=SubmissionStatusChoices.ACCEPTED, score=1)
            Submission.objects.create(user=st, task=t1, version=2, status=SubmissionStatusChoices.ACCEPTED, score=10 + i)
            # Month 2: reverse order via adjustments
            ScoreAdjustment.objects.create(user=st, admin=mentor, amount=200 - i * 10, reason='M2 Bonus', month=2)

        api = APIClient()
        api.force_authenticate(students[0])

        # Month 1: only month 1 counts, paginated, constant SQL queries (no N+1)
        with self.assertNumQueries(2):
            r_m1 = api.get('/api/v1/leaderboard', {'month': 1, 'page': 2, 'limit': 5})
        self.assertEqual(r_m1.status_code, 200)
        d_m1 = r_m1.json()
        self.assertEqual(d_m1['month'], 1)
        self.assertEqual(d_m1['total'], 12)
        self.assertEqual(d_m1['totalPages'], 3)
        self.assertEqual(len(d_m1['leaderboard']), 5)
        self.assertEqual([row['rank'] for row in d_m1['leaderboard']], [6, 7, 8, 9, 10])
        self.assertEqual(d_m1['leaderboard'][0]['totalScore'], 16)

        # Month 2: lb_stud_00 has 200 pts in month 2 (month 1 ignored)
        r_m2 = api.get('/api/v1/leaderboard', {'month': 2, 'limit': 3})
        self.assertEqual(r_m2.status_code, 200)
        self.assertEqual(r_m2.json()['month'], 2)
        self.assertEqual(r_m2.json()['leaderboard'][0]['login'], 'lb_stud_00')
        self.assertEqual(r_m2.json()['leaderboard'][0]['totalScore'], 200)

        # No month param -> all-time sum (10 + 200 = 210 for lb_stud_00)
        with self.assertNumQueries(2):
            r_all = api.get('/api/v1/leaderboard', {'limit': 5})
        self.assertEqual(r_all.status_code, 200)
        self.assertIsNone(r_all.json()['month'])
        self.assertEqual(r_all.json()['leaderboard'][0]['login'], 'lb_stud_00')
        self.assertEqual(r_all.json()['leaderboard'][0]['totalScore'], 210)

    def test_bug_034_telegram_dedupe_polling_offset_broadcast_and_retry(self):
        from unittest.mock import MagicMock, patch
        from admin_panel.models import TelegramOutbox, TelegramUpdate
        from admin_panel.services import outbox_service, telegram_service as tg

        # 1. Duplicate update_id processed once
        upd = {'update_id': 9001, 'message': {'chat': {'id': 88, 'type': 'private'}, 'from': {'id': 88}, 'text': '/help'}}
        self.assertTrue(tg.process_telegram_update(upd))
        self.assertFalse(tg.process_telegram_update(upd))
        self.assertEqual(TelegramUpdate.objects.filter(update_id=9001).count(), 1)
        self.assertEqual(TelegramOutbox.objects.count(), 1)

        # 2. Polling advances offset ONLY after successful processing
        updates_batch = [
            {'update_id': 9002, 'message': {'chat': {'id': 89, 'type': 'private'}, 'from': {'id': 89}, 'text': '/help'}},
            {'update_id': 9003, 'message': {'chat': {'id': 90, 'type': 'private'}, 'from': {'id': 90}, 'text': '/help'}},
        ]
        mock_resp = MagicMock(status_code=200, json=lambda: {'ok': True, 'result': updates_batch})
        with patch.object(tg, 'get_bot_token', return_value='tok'), \
             patch.object(tg.httpx, 'Client') as mock_client, \
             patch.object(tg, 'process_telegram_update', side_effect=[True, RuntimeError('boom')]):
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            next_offset = tg.run_telegram_polling(max_cycles=1)
        # 9002 succeeded -> offset moves to 9003, NOT 9004 because 9003 failed
        self.assertEqual(next_offset, 9003)

        # 3. Broadcast continues after individual enqueue failure
        with patch.object(outbox_service, 'enqueue', side_effect=[RuntimeError('bad row'), True]):
            res = tg.async_broadcast_message(['111', '222'], 'Hello all')
        self.assertEqual(res['errors'], 1)

        # 4. Real failure records concrete last_error and retry_outbox_queryset retries it
        TelegramOutbox.objects.all().delete()
        with self.settings(TELEGRAM_OUTBOX_EAGER=False):
            outbox_service.enqueue('777', 'Retry test', dedupe_key='err-retry-1')
        item = TelegramOutbox.objects.get(dedupe_key='err-retry-1')
        bad_http = MagicMock(status_code=400, json=lambda: {'ok': False, 'description': 'Bad Request: chat not found'}, text='')
        with patch.object(tg, 'get_bot_token', return_value='tok'), \
             patch.object(tg.httpx, 'Client') as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = bad_http
            self.assertFalse(outbox_service.deliver(item.pk))
        item.refresh_from_db()
        self.assertIn('chat not found', item.last_error)

        item.status = 'failed'
        item.save()
        ok_http = MagicMock(status_code=200, json=lambda: {'ok': True, 'result': {'message_id': 1}}, text='')
        with patch.object(tg, 'get_bot_token', return_value='tok'), \
             patch.object(tg.httpx, 'Client') as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = ok_http
            retry_res = outbox_service.retry_outbox_queryset(TelegramOutbox.objects.filter(pk=item.pk), drain_now=True)
        self.assertEqual(retry_res, {'queued': 1, 'sent': 1})
        item.refresh_from_db()
        self.assertEqual(item.status, 'sent')
        self.assertEqual(item.last_error, '')

    def test_bug_035_password_validators_and_legacy_hash_compat(self):
        import bcrypt
        import hashlib
        from admin_panel.serializers import RegisterSerializer, ChangePasswordSerializer

        for weak_pw in ('short1!', 'password123', '123456789', 'student_test'):
            ser = RegisterSerializer(data={'login': 'student_test', 'password': weak_pw, 'groupNumber': 'js-01'})
            self.assertFalse(ser.is_valid(), f'Weak password unexpectedly accepted: {weak_pw}')

        ok_ser = RegisterSerializer(data={'login': 'student_test', 'password': 'ValidPass#2026', 'groupNumber': 'js-01'})
        self.assertTrue(ok_ser.is_valid(), ok_ser.errors)

        bad_change = ChangePasswordSerializer(data={'currentPassword': 'x', 'newPassword': '123456789'})
        self.assertFalse(bad_change.is_valid())

        # Legacy SHA-256 + bcrypt login stays intact
        legacy_pw = 'LegacyLogin#2026'
        legacy_hash = bcrypt.hashpw(hashlib.sha256(legacy_pw.encode()).hexdigest().encode(), bcrypt.gensalt()).decode()
        u = create_user(login='legacy_sha_user', password_hash=legacy_hash, password_uses_sha256=True, role=RoleChoices.STUDENT)
        resp = self.client.post(
            '/api/v1/auth/login',
            data=json.dumps({'login': u.login, 'password': legacy_pw}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

    def test_platform_settings_system_config_and_runtime_wiring(self):
        from django.core.exceptions import ValidationError
        from rest_framework.test import APIClient
        from admin_panel.models import PlatformSetting
        from admin_panel.services.media_service import get_media_limit
        from admin_panel.services.settings_service import ensure_default_settings, get_setting

        ensure_default_settings()
        self.assertGreaterEqual(PlatformSetting.objects.count(), 25)

        # Security guardrail: default_role cannot be ADMIN
        role_setting = PlatformSetting.objects.get(key='default_role')
        role_setting.value = 'ADMIN'
        with self.assertRaises(ValidationError):
            role_setting.full_clean()

        # Dynamic branding updates invalidate system/config cache automatically
        PlatformSetting.objects.filter(key='platform_name').update(value='Merts Academy')
        PlatformSetting.objects.get(key='platform_name').save()
        cfg_resp = self.client.get('/api/v1/system/config')
        self.assertEqual(cfg_resp.status_code, 200)
        cfg_data = cfg_resp.json()
        self.assertEqual(cfg_data['platform']['name'], 'Merts Academy')
        self.assertIn('features', cfg_data)
        self.assertIn('gamification', cfg_data)

        # Dynamic upload limit (1 MB)
        av_setting = PlatformSetting.objects.get(key='avatar_max_mb')
        av_setting.value = '1'
        av_setting.full_clean()
        av_setting.save()
        self.assertEqual(get_media_limit('AVATAR'), 1 * 1024 * 1024)
        self.assertEqual(self.client.get('/api/v1/system/config').json()['uploadLimits']['avatarMaxBytes'], 1024 * 1024)

        # Dynamic default_task_points * bonus_task_multiplier
        PlatformSetting.objects.filter(key='default_task_points').update(value='15')
        PlatformSetting.objects.get(key='default_task_points').save()
        PlatformSetting.objects.filter(key='bonus_task_multiplier').update(value='3')
        PlatformSetting.objects.get(key='bonus_task_multiplier').save()
        bonus_task = Task.objects.create(title='Dynamic Bonus', topic='Py', is_bonus=True, has_score=True, max_score=None)
        self.assertEqual(bonus_task.max_score, 45)

        # registration_open = false blocks /api/v1/auth/register
        reg_open = PlatformSetting.objects.get(key='registration_open')
        reg_open.value = 'false'
        reg_open.save()
        blocked_reg = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps({'login': 'blocked_st', 'password': 'ValidPass#2026', 'groupNumber': 'js-01'}),
            content_type='application/json',
        )
        self.assertEqual(blocked_reg.status_code, 403)
        reg_open.value = 'true'
        reg_open.save()

        # easter_egg_enabled = false blocks /api/v1/users/me/easter-egg
        st = create_user(login='egg_stud', role=RoleChoices.STUDENT, telegram_chat_id='555111')
        api = APIClient()
        api.force_authenticate(st)
        egg = PlatformSetting.objects.get(key='easter_egg_enabled')
        egg.value = 'false'
        egg.save()
        self.assertEqual(api.post('/api/v1/users/me/easter-egg').status_code, 403)
        egg.value = 'true'
        egg.save()

    def test_telegram_templates_toggles_and_admin_actions(self):
        from unittest.mock import patch
        from admin_panel.models import PlatformSetting, TelegramOutbox, MonthlyScoreArchive
        from admin_panel.services.achievement_service import ensure_default_achievements
        from admin_panel.services.settings_service import ensure_default_settings

        ensure_default_settings()
        ensure_default_achievements()

        st = create_user(login='tpl_student', name='Мария', group_number='js-01', current_month=1, telegram_chat_id='998877', streak_count=7)
        mentor = create_user(login='tpl_mentor', role=RoleChoices.ADMIN)

        # Toggle off lesson notification
        tgl = PlatformSetting.objects.get(key='tg_notify_lesson_published')
        tgl.value = 'false'
        tgl.save()
        Lesson.objects.create(title='Silent Lesson', group_number='js-01', month=1, youtube_id='abcdefghijk')
        self.assertEqual(TelegramOutbox.objects.count(), 0)

        # Custom submission review template with unknown placeholder safely rendered
        tpl = PlatformSetting.objects.get(key='tg_template_submission_reviewed')
        tpl.value = 'Привет, {student_name}! {task_title} -> {status} | {score}{unknown_field}'
        tpl.save()
        task = Task.objects.create(title='ДЗ-1', topic='Py', month=1, group_number='js-01', max_score=20)
        TelegramOutbox.objects.all().delete()
        with self.settings(TELEGRAM_OUTBOX_EAGER=True), \
             patch('admin_panel.services.telegram_service.send_telegram_message', return_value=True) as mock_send:
            Submission.objects.create(user=st, task=task, status=SubmissionStatusChoices.ACCEPTED, score=18)
        self.assertTrue(mock_send.called)
        sent_text = mock_send.call_args.kwargs['text']
        self.assertIn('Привет, Мария! ДЗ-1', sent_text)
        self.assertNotIn('{unknown_field}', sent_text)

        # Dual-case snake_case registration + Tasks search/filtering/pagination
        snake_reg = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps({'login': 'snake_user', 'password': 'ValidPass#2026', 'group_number': 'js-01'}),
            content_type='application/json',
        )
        self.assertEqual(snake_reg.status_code, 201)
        token = snake_reg.json()['accessToken']
        Task.objects.create(title='Обычное ДЗ', topic='Git', month=1, group_number='js-01', is_bonus=False)
        Task.objects.create(title='Бонус React', topic='React', month=1, group_number='js-01', is_bonus=True)
        t_resp = self.client.get(
            '/api/v1/tasks',
            {'is_bonus': 'true', 'search': 'React', 'ordering': '-order', 'page': 1, 'limit': 5},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(t_resp.status_code, 200)
        self.assertEqual(t_resp.json()['total'], 1)
        self.assertEqual(t_resp.json()['tasks'][0]['title'], 'Бонус React')

        # PlatformSettingAdmin permissions & UserAdmin bulk actions
        with override_settings(PLATFORM_OWNER_ADMIN_ID=str(self.owner.pk)):
            self.client.force_login(self.owner)
            self.assertEqual(self.client.get('/admin/admin_panel/platformsetting/').status_code, 200)

            staff_only = User.objects.create(login='junior_staff', password_hash='x', role=RoleChoices.ADMIN, id='999999')
            from django.contrib.auth import get_user_model
            non_owner_dj = get_user_model().objects.create_user(username='junior_staff', password='Staff-Password-2026!', is_staff=True)
            self.client.force_login(non_owner_dj)
            self.assertEqual(self.client.get('/admin/admin_panel/platformsetting/').status_code, 403)
            self.assertEqual(self.client.get(f'/admin/admin_panel/platformsetting/{tpl.pk}/change/').status_code, 403)
            self.assertEqual(
                self.client.post(f'/admin/admin_panel/platformsetting/{tpl.pk}/change/', {'value': 'tampered'}).status_code,
                403,
            )
            self.assertEqual(self.client.get('/admin/admin_panel/platformsetting/add/').status_code, 403)
            staff_only.delete()

            self.client.force_login(self.owner)
            self.client.post('/admin/admin_panel/user/', {'action': 'recalculate_student_scores', '_selected_action': [st.pk]})
            self.assertEqual(MonthlyScoreArchive.objects.get(user=st, month=1).final_score, 18)

            self.client.post('/admin/admin_panel/user/', {'action': 'reevaluate_achievements', '_selected_action': [st.pk]})
            self.assertTrue(UserAchievement.objects.filter(user=st, achievement__code='STREAK_MASTER').exists())

            TelegramOutbox.objects.all().delete()
            broadcast_resp = self.client.post('/admin/admin_panel/user/', {
                'action': 'send_custom_telegram_message',
                '_selected_action': [st.pk],
                'apply': '1',
                'message_text': 'Важное объявление!',
            })
            self.assertEqual(broadcast_resp.status_code, 302)
            self.assertEqual(TelegramOutbox.objects.filter(chat_id='998877').count(), 1)

    def test_instruction_pdf_upload_serving_and_admin_replacement(self):
        from pathlib import Path
        from unittest.mock import patch
        from django.contrib import admin
        from django.contrib.auth import get_user_model
        from django.core.files.uploadedfile import SimpleUploadedFile
        from admin_panel.admin import MediaAssetAdmin
        from admin_panel.models import PlatformSetting
        from admin_panel.services.media_service import (
            DEFAULT_INSTRUCTION_PDF_PATH,
            get_media_limit,
            save_optimized_media_asset,
        )

        # 1. system/config exposes instructionPdfUrl and keeps instruction_pdf_asset_id private
        cfg = self.client.get('/api/v1/system/config').json()
        expected_url = 'https://166.0.28.165.sslip.io/api/v1/media/instruction'
        self.assertEqual(cfg['platform']['instructionPdfUrl'], expected_url)
        self.assertEqual(cfg['settings']['instruction_pdf_url'], expected_url)
        self.assertNotIn('instruction_pdf_asset_id', cfg['settings'])

        # 2. Default bundled PDF is served when DB has no DOCUMENT asset
        default_resp = self.client.get('/api/v1/media/instruction')
        self.assertEqual(default_resp.status_code, 200)
        self.assertEqual(default_resp['Content-Type'], 'application/pdf')
        self.assertEqual(
            default_resp['Content-Disposition'],
            'attachment; filename="MertsPlatform_Instruction.pdf"',
        )
        self.assertTrue(default_resp.content.startswith(b'%PDF-'))
        self.assertEqual(default_resp.content, DEFAULT_INSTRUCTION_PDF_PATH.read_bytes())

        # 3. Missing both DB asset and default file returns 404 JSON
        with patch('admin_panel.views.media_views.DEFAULT_INSTRUCTION_PDF_PATH', Path('/nonexistent/instruction.pdf')):
            missing_resp = self.client.get('/api/v1/media/instruction')
        self.assertEqual(missing_resp.status_code, 404)
        self.assertEqual(missing_resp.json()['statusCode'], 404)

        # 4. Media service DOCUMENT validation & storage without Pillow
        sample_pdf = b'%PDF-1.4\n%sample instruction v1\n%%EOF\n'
        with self.assertRaises(ValueError):
            save_optimized_media_asset(sample_pdf, 'text/html', kind='DOCUMENT')
        with self.assertRaises(ValueError):
            save_optimized_media_asset(b'not-a-pdf', 'application/pdf', kind='DOCUMENT')
        with self.assertRaises(ValueError):
            save_optimized_media_asset(b'%PDF-' + b'0' * get_media_limit('DOCUMENT'), 'application/pdf', kind='DOCUMENT')

        with patch('admin_panel.services.media_service.Image.open', side_effect=AssertionError('Pillow must not run for PDF')):
            saved = save_optimized_media_asset(sample_pdf, 'application/pdf', kind='DOCUMENT')
        self.assertEqual(saved['mimeType'], 'application/pdf')
        db_resp = self.client.get('/api/v1/media/instruction')
        self.assertEqual(db_resp.status_code, 200)
        self.assertEqual(db_resp.content, sample_pdf)

        # 5. Admin upload/replacement workflow and permissions
        upload_url = '/admin/admin_panel/mediaasset/upload-instruction-pdf/'
        staff_user = get_user_model().objects.create_user(
            username='pdf_staff', password='Staff-Password-2026!', is_staff=True
        )
        updated_pdf = b'%PDF-1.7\n%updated instruction v2\n%%EOF\n'

        with override_settings(PLATFORM_OWNER_ADMIN_ID=str(self.owner.pk)):
            self.client.force_login(staff_user)
            self.assertEqual(self.client.get(upload_url).status_code, 403)
            self.assertEqual(
                self.client.post(
                    upload_url,
                    {'pdf_file': SimpleUploadedFile('inst.pdf', updated_pdf, content_type='application/pdf')},
                ).status_code,
                403,
            )

            self.client.force_login(self.owner)
            self.assertEqual(self.client.get(upload_url).status_code, 200)

            bad_post = self.client.post(
                upload_url,
                {'pdf_file': SimpleUploadedFile('bad.pdf', b'not-pdf', content_type='application/pdf')},
            )
            self.assertEqual(bad_post.status_code, 200)
            self.assertEqual(MediaAsset.objects.filter(kind='DOCUMENT').count(), 1)

            good_post = self.client.post(
                upload_url,
                {'pdf_file': SimpleUploadedFile('MertsPlatform_Instruction.pdf', updated_pdf, content_type='application/octet-stream')},
            )
            self.assertEqual(good_post.status_code, 302)
            changelist_resp = self.client.get('/admin/admin_panel/mediaasset/')
            self.assertEqual(changelist_resp.status_code, 200)
            self.assertContains(changelist_resp, 'upload-instruction-pdf')
            settings_redirect = self.client.get('/admin/admin_panel/platformsetting/upload-instruction-pdf/')
            self.assertEqual(settings_redirect.status_code, 302)
            self.assertTrue(settings_redirect['Location'].endswith('/admin/admin_panel/mediaasset/upload-instruction-pdf/'))

        self.assertEqual(MediaAsset.objects.filter(kind='DOCUMENT').count(), 2)
        active_id = PlatformSetting.objects.get(key='instruction_pdf_asset_id').value
        new_asset = MediaAsset.objects.get(pk=active_id)
        self.assertEqual(new_asset.kind, 'DOCUMENT')
        self.assertEqual(new_asset.mime_type, 'application/pdf')

        self.client.logout()
        final_resp = self.client.get('/api/v1/media/instruction')
        self.assertEqual(final_resp.status_code, 200)
        self.assertEqual(final_resp['Content-Type'], 'application/pdf')
        self.assertEqual(
            final_resp['Content-Disposition'],
            'attachment; filename="MertsPlatform_Instruction.pdf"',
        )
        self.assertEqual(final_resp.content, updated_pdf)

        # 6. MediaAssetAdmin renders PDF badge with 0 extra queries
        ma_admin = MediaAssetAdmin(MediaAsset, admin.site)
        with self.assertNumQueries(0):
            preview_html = str(ma_admin.asset_preview(new_asset))
        self.assertIn('PDF', preview_html)
        self.assertNotIn('<img', preview_html)

    def test_achievement_admin_creation_validation_recalculate_and_api(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from rest_framework.test import APIClient
        from admin_panel.authentication import generate_tokens_for_user

        self.client.force_login(self.owner)
        add_url = '/admin/admin_panel/achievement/add/'
        list_url = '/admin/admin_panel/achievement/'

        # 0. Add form page loads cleanly
        self.assertEqual(self.client.get(add_url).status_code, 200)

        # 1. Auto-generate UPPER_SNAKE_CASE code from Russian title + preset icon
        r1 = self.client.post(
            add_url,
            {
                'title': 'Мастер Кода!',
                'code': '',
                'description': 'За высокие баллы',
                'category': 'SCORES',
                'is_active': 'on',
                'preset_icon': '/api/v1/media/presets/icons/crown.svg',
                'trigger_type': 'TOTAL_SCORE',
                'threshold': '20',
                'points': '15',
            },
        )
        self.assertEqual(r1.status_code, 302)
        auto_ach = Achievement.objects.get(code='MASTER_KODA')
        self.assertEqual(auto_ach.icon_url, '/api/v1/media/presets/icons/crown.svg')
        self.assertEqual(auto_ach.threshold, 20)
        self.assertTrue(bool(auto_ach.criteria))

        # 2. Duplicate title generates _2 suffix
        r2 = self.client.post(
            add_url,
            {
                'title': 'Мастер Кода!',
                'code': '',
                'description': 'Вторая версия',
                'category': 'SCORES',
                'is_active': 'on',
                'preset_icon': '/api/v1/media/presets/icons/star.svg',
                'trigger_type': 'TOTAL_SCORE',
                'threshold': '30',
                'points': '20',
            },
        )
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(Achievement.objects.filter(code='MASTER_KODA_2').exists())

        # 3. Missing preset_icon and custom_icon_file fails validation
        r3 = self.client.post(
            add_url,
            {
                'title': 'Без иконки',
                'code': '',
                'description': 'Нет картинки',
                'category': 'TASKS',
                'is_active': 'on',
                'trigger_type': 'MANUAL',
                'points': '5',
            },
        )
        self.assertEqual(r3.status_code, 200)
        self.assertIn('preset_icon', r3.context['adminform'].form.errors)
        self.assertFalse(Achievement.objects.filter(title='Без иконки').exists())

        # 4. Numeric trigger with invalid threshold + valid PNG creates NO orphan MediaAsset
        png_buf = io.BytesIO()
        Image.new('RGB', (24, 24), color=(245, 158, 11)).save(png_buf, format='PNG')
        png_bytes = png_buf.getvalue()

        r4 = self.client.post(
            add_url,
            {
                'title': 'Без порога',
                'code': '',
                'description': 'Ошибка порога',
                'category': 'TASKS',
                'is_active': 'on',
                'trigger_type': 'ACCEPTED_TASKS',
                'threshold': '0',
                'points': '10',
                'custom_icon_file': SimpleUploadedFile('badge.png', png_bytes, content_type='image/png'),
            },
        )
        self.assertEqual(r4.status_code, 200)
        self.assertIn('threshold', r4.context['adminform'].form.errors)
        self.assertEqual(MediaAsset.objects.filter(kind='ACHIEVEMENT_ICON').count(), 0)
        self.assertFalse(Achievement.objects.filter(title='Без порога').exists())

        # SVG custom upload is rejected with validation error
        r_svg = self.client.post(
            add_url,
            {
                'title': 'Плохой SVG',
                'code': '',
                'description': 'SVG тест',
                'category': 'SPECIAL',
                'is_active': 'on',
                'trigger_type': 'MANUAL',
                'points': '10',
                'custom_icon_file': SimpleUploadedFile('bad.svg', b'<svg><script/></svg>', content_type='image/svg+xml'),
            },
        )
        self.assertEqual(r_svg.status_code, 200)
        self.assertIn('custom_icon_file', r_svg.context['adminform'].form.errors)
        self.assertEqual(MediaAsset.objects.filter(kind='ACHIEVEMENT_ICON').count(), 0)

        # 5. MANUAL clears threshold=99 -> None and saves custom PNG -> WebP MediaAsset
        r5 = self.client.post(
            add_url,
            {
                'title': 'Особая Награда',
                'code': '',
                'description': 'Ручная награда',
                'category': 'SPECIAL',
                'is_active': 'on',
                'trigger_type': 'MANUAL',
                'threshold': '99',
                'points': '50',
                'custom_icon_file': SimpleUploadedFile('custom.png', png_bytes, content_type='image/png'),
            },
        )
        self.assertEqual(r5.status_code, 302)
        manual_ach = Achievement.objects.get(code='OSOBAYA_NAGRADA')
        self.assertIsNone(manual_ach.threshold)
        self.assertTrue(manual_ach.icon_url.startswith('/api/v1/media/'))
        asset_id = manual_ach.icon_url.rsplit('/', 1)[-1]
        self.assertEqual(MediaAsset.objects.get(pk=asset_id).mime_type, 'image/webp')

        # 6. Editing system achievement preserves its code & custom criteria, while rule edit updates auto criteria
        ensure_default_achievements()
        welcome_ach = Achievement.objects.get(code='WELCOME')
        original_welcome_criteria = welcome_ach.criteria
        r6 = self.client.post(
            f'/admin/admin_panel/achievement/{welcome_ach.pk}/change/',
            {
                'title': welcome_ach.title,
                'code': 'TAMPERED_CODE',
                'description': welcome_ach.description,
                'category': welcome_ach.category,
                'is_active': 'on',
                'preset_icon': welcome_ach.icon_url,
                'trigger_type': welcome_ach.trigger_type,
                'points': str(welcome_ach.points),
            },
        )
        self.assertEqual(r6.status_code, 302)
        welcome_ach.refresh_from_db()
        self.assertEqual(welcome_ach.code, 'WELCOME')
        self.assertEqual(welcome_ach.criteria, original_welcome_criteria)

        ach_v2 = Achievement.objects.get(code='MASTER_KODA_2')
        r6_rule = self.client.post(
            f'/admin/admin_panel/achievement/{ach_v2.pk}/change/',
            {
                'title': ach_v2.title,
                'code': ach_v2.code,
                'description': ach_v2.description,
                'category': ach_v2.category,
                'is_active': 'on',
                'preset_icon': ach_v2.icon_url,
                'trigger_type': 'TOTAL_SCORE',
                'threshold': '45',
                'points': str(ach_v2.points),
            },
        )
        self.assertEqual(r6_rule.status_code, 302)
        ach_v2.refresh_from_db()
        self.assertIn('45', ach_v2.criteria)

        # 7. Changelist renders 32x32 icon with fallback, annotated awarded count and no N+1 across rows
        mentor = create_user(login='ach_adm_mentor', role=RoleChoices.ADMIN)
        s1 = create_user(login='ach_adm_stud1', role=RoleChoices.STUDENT)
        s2 = create_user(login='ach_adm_stud2', role=RoleChoices.STUDENT)
        with CaptureQueriesContext(connection) as q_before:
            changelist_1 = self.client.get(list_url)
        self.assertEqual(changelist_1.status_code, 200)
        self.assertContains(changelist_1, 'width="32" height="32"')
        self.assertContains(changelist_1, 'data-fallback="data:image/svg+xml;base64,')

        UserAchievement.objects.create(user=s1, achievement=welcome_ach)
        UserAchievement.objects.create(user=s2, achievement=welcome_ach)
        UserAchievement.objects.create(user=s1, achievement=manual_ach)
        with CaptureQueriesContext(connection) as q_after:
            changelist_2 = self.client.get(list_url)
        self.assertEqual(changelist_2.status_code, 200)
        self.assertLessEqual(len(q_after), len(q_before) + 1)

        # 8a. Automatic trigger via achievement_service on score gain
        ScoreAdjustment.objects.create(user=s1, admin=mentor, amount=25, reason='Bonus', month=1)
        self.assertTrue(UserAchievement.objects.filter(user=s1, achievement=auto_ach).exists())

        # 8b. Retroactive admin action recalculates selected auto achievements (skips MANUAL)
        r_retro = self.client.post(
            add_url,
            {
                'title': 'Ретро Лидер',
                'code': '',
                'description': 'Создана после начисления баллов',
                'category': 'SCORES',
                'is_active': 'on',
                'preset_icon': '/api/v1/media/presets/icons/trophy.svg',
                'trigger_type': 'TOTAL_SCORE',
                'threshold': '25',
                'points': '25',
            },
        )
        self.assertEqual(r_retro.status_code, 302)
        retro_ach = Achievement.objects.get(code='RETRO_LIDER')
        self.assertFalse(UserAchievement.objects.filter(user=s1, achievement=retro_ach).exists())

        act_resp = self.client.post(
            list_url,
            {
                'action': 'recalculate_and_award_students',
                '_selected_action': [retro_ach.pk, manual_ach.pk],
            },
            follow=True,
        )
        self.assertEqual(act_resp.status_code, 200)
        self.assertContains(act_resp, 'Выдано новых наград: 1.')
        self.assertTrue(UserAchievement.objects.filter(user=s1, achievement=retro_ach).exists())
        self.assertFalse(UserAchievement.objects.filter(user=s2, achievement=retro_ach).exists())
        self.assertFalse(UserAchievement.objects.filter(user=s2, achievement=manual_ach).exists())

        # 9. GET /api/v1/achievements returns created items with absolute iconUrl and unlocked state
        api = APIClient()
        tok, _, _ = generate_tokens_for_user(s1)
        api.credentials(HTTP_AUTHORIZATION='Bearer ' + tok)
        api_resp = api.get('/api/v1/achievements', {'limit': 50})
        self.assertEqual(api_resp.status_code, 200)
        by_code = {item['code']: item for item in api_resp.json()['achievements']}
        self.assertIn('MASTER_KODA', by_code)
        self.assertIn('OSOBAYA_NAGRADA', by_code)
        self.assertEqual(
            by_code['MASTER_KODA']['iconUrl'],
            'http://testserver/api/v1/media/presets/icons/crown.svg',
        )
        self.assertTrue(by_code['MASTER_KODA']['isUnlocked'])
        self.assertTrue(by_code['MASTER_KODA']['isUnlockedByMe'])
        self.assertEqual(
            by_code['OSOBAYA_NAGRADA']['iconUrl'],
            f'http://testserver{manual_ach.icon_url}',
        )
