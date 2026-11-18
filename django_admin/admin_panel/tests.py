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
        # Closed registration; existing provisioned accounts still authenticate.
        reg_resp = self.client.post('/api/v1/auth/register', data={}, content_type='application/json')
        self.assertEqual(reg_resp.status_code, 403)
        user = User(login='test_student', has_subscription=True, group_number='GRP-101')
        user.set_password('Password123!')
        user.save()
        subscribe(user)
        from admin_panel.services.achievement_service import evaluate_user_achievements
        evaluate_user_achievements(user.id, trigger_filter='ON_REGISTER')
        self.assertEqual(UserAchievement.objects.filter(user=user, achievement__code='WELCOME').count(), 1)

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
        icon_url = form2.cleaned_data['icon_url']
        self.assertTrue(icon_url.startswith('/api/v1/media/'))

        # Verify MediaAsset record in DB
        media_id = icon_url.split('/')[-1]
        asset = MediaAsset.objects.get(id=media_id)
        self.assertEqual(asset.kind, 'ACHIEVEMENT_ICON')
        self.assertEqual(asset.mime_type, 'image/webp')

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
        lesson_admin.message_user = lambda req, msg: mock_messages.append(msg)
        with patch('admin_panel.services.telegram_service.async_broadcast_message', return_value={'sent': 1, 'errors': 0}):
            lesson_admin.broadcast_lesson_telegram(mock_request, Lesson.objects.filter(id=lesson.id))
        self.assertEqual(len(mock_messages), 1)
        self.assertEqual('Отправлено: 1, Ошибок: 0', mock_messages[0])

        task_admin = TaskAdmin(Task, site)
        task_admin.message_user = lambda req, msg: mock_messages.append(msg)
        with patch('admin_panel.services.telegram_service.async_broadcast_message', return_value={'sent': 1, 'errors': 0}):
            task_admin.broadcast_task_telegram(mock_request, Task.objects.filter(id=task.id))
        self.assertEqual(len(mock_messages), 2)
        self.assertEqual('Отправлено: 1, Ошибок: 0', mock_messages[1])

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
        reg_payload = {
            "login": "student_group_test",
            "password": "Password123!",
            "groupNumber": "js-02",
            "name": "Студент Группы 2",
        }
        resp = self.client.post('/api/v1/auth/register', data=json.dumps(reg_payload), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        StudyGroup.objects.get_or_create(name="js-02", defaults={"month": 2})
        user_group = create_user(has_subscription=True, login="student_group_test", password_hash="hash", group_number="js-02")
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
