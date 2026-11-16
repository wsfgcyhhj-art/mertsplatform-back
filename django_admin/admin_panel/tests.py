from django.utils import timezone
import io
import json
from PIL import Image
from django.test import TransactionTestCase, Client
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
    RoleChoices,
    SubmissionStatusChoices,
)
from admin_panel.services.achievement_service import ensure_default_achievements

UNMANAGED_MODELS = [
    User,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    Achievement,
    UserAchievement,
    MediaAsset,
    Session,
]


class MertsPlatformFullAPITestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            for m in UNMANAGED_MODELS:
                try:
                    editor.create_model(m)
                except Exception:
                    pass

    def setUp(self):
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
        # 1. Register student
        reg_payload = {
            "login": "test_student",
            "password": "Password123!",
            "groupNumber": "GRP-101",
            "name": "Иван Студентов",
        }
        reg_resp = self.client.post(
            '/api/v1/auth/register',
            data=json.dumps(reg_payload),
            content_type='application/json'
        )
        self.assertEqual(reg_resp.status_code, 201)
        reg_data = reg_resp.json()
        self.assertIn('accessToken', reg_data)
        user_id = reg_data['user']['id']

        # Verify ON_REGISTER achievement (WELCOME)
        ach_count = UserAchievement.objects.filter(user_id=user_id, achievement__code='WELCOME').count()
        self.assertEqual(ach_count, 1)

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

        # 3. Refresh token
        refresh_token = login_data['refreshToken']
        refresh_resp = self.client.post(
            '/api/v1/auth/refresh',
            data=json.dumps({"refreshToken": refresh_token}),
            content_type='application/json'
        )
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertIn('accessToken', refresh_resp.json())

    def test_04_user_profile_and_password_update(self):
        # Create user
        user = User.objects.create(
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
        user = User.objects.create(login='student_media', role=RoleChoices.STUDENT)
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
        self.assertTrue(avatar_url.startswith('/api/v1/media/'))

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
        mentor = User.objects.create(login='mentor_test', role=RoleChoices.ADMIN)
        mentor.set_password('MentorPass123')
        mentor.save()

        student = User.objects.create(login='student_hw', role=RoleChoices.STUDENT, group_number='GRP-1')
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
        s1 = User.objects.create(login='stud1', role=RoleChoices.STUDENT, current_month=1)
        s2 = User.objects.create(login='stud2', role=RoleChoices.STUDENT, current_month=1)
        s1.set_password('Pass123!')
        s2.set_password('Pass123!')
        s1.save()
        s2.save()

        # Score adjustments: stud2 has 30, stud1 has 10
        admin = User.objects.create(login='admin_adj', role=RoleChoices.ADMIN)
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
        user = User.objects.create(login='tg_user', role=RoleChoices.STUDENT)
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
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>'
        uploaded_file = SimpleUploadedFile(
            name="custom_badge.svg",
            content=svg_content,
            content_type="image/svg+xml"
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
        icon_url = form2.cleaned_data['icon_url']
        self.assertTrue(icon_url.startswith('/api/v1/media/'))

        # Verify MediaAsset record in DB
        media_id = icon_url.split('/')[-1]
        asset = MediaAsset.objects.get(id=media_id)
        self.assertEqual(asset.kind, 'ACHIEVEMENT_ICON')
        self.assertEqual(asset.mime_type, 'image/svg+xml')

        # 3. Test AchievementAdmin badges
        site = AdminSite()
        admin_obj = AchievementAdmin(Achievement, site)
        ach_instance = Achievement(code='CUSTOM_UPLOAD_TEST', icon_url=icon_url)
        preview_html = admin_obj.icon_preview(ach_instance)
        self.assertIn(f'src="{icon_url}"', preview_html)
        badge_html = admin_obj.icon_source_badge(ach_instance)
        self.assertIn('Кастомный файл (Neon DB)', badge_html)

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
        admin_user = User.objects.create(
            login='admin_notif',
            name='Админ Уведомлений',
            password_hash='hash123',
            role=RoleChoices.ADMIN,
            telegram_chat_id='111222333',
        )
        student = User.objects.create(
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
        ach = Achievement.objects.get(code='WELCOME')
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
            self.assertIn('Корректировка баллов!', message)
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
        lesson_admin.message_user = lambda req, msg: mock_messages.append(msg)
        with patch('admin_panel.services.telegram_service.async_broadcast_message'):
            lesson_admin.broadcast_lesson_telegram(mock_request, Lesson.objects.filter(id=lesson.id))
        self.assertEqual(len(mock_messages), 1)
        self.assertIn('поставлены в очередь', mock_messages[0])

        task_admin = TaskAdmin(Task, site)
        task_admin.message_user = lambda req, msg: mock_messages.append(msg)
        with patch('admin_panel.services.telegram_service.async_broadcast_message'):
            task_admin.broadcast_task_telegram(mock_request, Task.objects.filter(id=task.id))
        self.assertEqual(len(mock_messages), 2)
        self.assertIn('поставлены в очередь', mock_messages[1])
