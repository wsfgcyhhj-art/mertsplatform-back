from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections, transaction
from django.test import Client, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient
from PIL import Image

from admin_panel.models import Achievement, ScoreAdjustment, ShopOrder, ShopOrderStatus, ShopProduct, Submission, Task, UserAchievement
from admin_panel.services.shop_service import ShopConflict, place_order, process_order, shop_balance
from admin_panel.test_support import clear_data, create_schema, create_user


class ShopTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_schema()

    def setUp(self):
        clear_data()
        self.student = create_user(login='buyer', has_subscription=True, streak_count=10)
        self.owner = get_user_model().objects.create_superuser(username='shop-owner', password='Shop-Owner-Password-2026!')
        self.product = ShopProduct.objects.create(title='Мерч', price_som=200, price_coins=40, stock=2)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def _grant_coins(self, user, points=50):
        ach, _ = Achievement.objects.get_or_create(
            code=f'SHOP_COIN_{points}',
            defaults={'title': f'Shop Coin {points}', 'points': points},
        )
        UserAchievement.objects.create(user=user, achievement=ach)

    @patch('admin_panel.signals.evaluate_user_achievements')
    def test_earned_points_are_separate_from_leaderboard(self, _evaluate):
        task = Task.objects.create(title='ДЗ', topic='Python')
        owner = create_user(login='mentor', role='ADMIN')
        for version, score, status in ((1, 20, 'ACCEPTED'), (2, 30, 'ACCEPTED'), (3, 0, 'REVISION')):
            Submission.objects.create(user=self.student, task=task, version=version, score=score, status=status)
        achievement = Achievement.objects.create(title='Стрик', code='SHOP_TEST', points=15)
        UserAchievement.objects.create(user=self.student, achievement=achievement)
        ScoreAdjustment.objects.create(user=self.student, admin=owner, amount=7, reason='Бонус', month=1)
        ScoreAdjustment.objects.create(user=self.student, admin=owner, amount=-2, reason='Штраф', month=1)
        profile = self.api.get('/api/v1/users/me').json()
        self.assertEqual(profile['stats']['totalScore'], 35)
        self.assertEqual(profile['totalEarnedPoints'], 50)
        self.assertEqual(self.api.get('/api/v1/shop/balance').json(),
                         {'totalEarnedPoints': 50, 'spentPoints': 0, 'availableCoins': 50})
        self.assertEqual(self.api.post('/api/v1/shop/orders', {'productId': self.product.pk}).status_code, 201)
        profile = self.api.get('/api/v1/users/me').json()
        self.assertEqual((profile['stats']['totalScore'], profile['availableCoins']), (35, 10))

    def test_order_retry_insufficient_balance_and_cancellation(self):
        self._grant_coins(self.student, 50)
        payload = {'productId': self.product.pk, 'requestId': str(uuid4())}
        stale = self.api.post('/api/v1/shop/orders', {**payload, 'expectedPriceCoins': 39})
        self.assertEqual(stale.status_code, 409)
        self.assertIn('Цена изменилась', stale.json()['detail'])
        response = self.api.post('/api/v1/shop/orders', payload)
        self.assertEqual(response.status_code, 201)
        order_id = response.json()['order']['id']
        self.assertEqual(response.json()['availableCoins'], 10)
        replay = self.api.post('/api/v1/shop/orders', payload)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()['order']['id'], order_id)
        self.assertEqual(self.api.post('/api/v1/shop/orders', {'productId': self.product.pk}).status_code, 409)
        self.assertEqual(len(self.api.get('/api/v1/shop/orders/my').json()), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

        admin = Client()
        admin.force_login(self.owner)
        with override_settings(PLATFORM_OWNER_ADMIN_ID=str(self.owner.pk)):
            response = admin.post('/admin/admin_panel/shoporder/', {
                'action': 'cancel_orders', '_selected_action': order_id, 'index': '0',
            })
        self.assertEqual(response.status_code, 302)
        cancelled = ShopOrder.objects.get(pk=order_id)
        self.assertEqual((cancelled.status, cancelled.processed_by), ('CANCELLED', self.owner.username))
        self.assertFalse(process_order(order_id, ShopOrderStatus.CANCELLED, self.owner))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(shop_balance(self.student)['availableCoins'], 50)

    @override_settings(TELEGRAM_OUTBOX_EAGER=True)
    def test_order_notifications_and_completed_order_cannot_be_cancelled(self):
        self._grant_coins(self.student, 50)
        mentor = create_user(login='mentor', role='ADMIN', telegram_chat_id='222')
        self.student.telegram_chat_id = '111'
        self.student.save()
        with self.settings(PLATFORM_OWNER_USER_ID=mentor.pk), patch(
            'admin_panel.services.telegram_service.send_telegram_message', return_value=True
        ) as send:
            with transaction.atomic():
                order, _, _ = place_order(self.student, self.product.pk, '')
                send.assert_not_called()
            self.assertEqual({call.args[0] for call in send.call_args_list}, {'111', '222'})
            send.reset_mock()
            self.assertTrue(process_order(order.pk, ShopOrderStatus.COMPLETED, self.owner))
            self.assertFalse(process_order(order.pk, ShopOrderStatus.CANCELLED, self.owner))
            self.assertEqual(send.call_args.args[0], '111')
            self.assertIn('Ваш мерч готов к выдаче', send.call_args.kwargs['text'])
        self.assertEqual(shop_balance(self.student)['availableCoins'], 10)

    def race_purchases(self, buyers):
        barrier = Barrier(2)

        def purchase(buyer):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                place_order(buyer, self.product.pk, '')
                return True
            except ShopConflict:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(executor.map(purchase, buyers), [True, False])
        self.assertEqual(ShopOrder.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_purchases_cannot_overspend(self):
        self._grant_coins(self.student, 50)
        self.race_purchases([self.student, self.student])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_buyers_cannot_buy_the_last_product(self):
        self._grant_coins(self.student, 50)
        other = create_user(login='other-buyer', has_subscription=True, streak_count=10)
        self._grant_coins(other, 50)
        self.product.stock = 1
        self.product.save(update_fields=['stock'])
        self.race_purchases([self.student, other])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_admin_uploads_product_image(self):
        png = BytesIO()
        Image.new('RGB', (10, 10), 'white').save(png, format='PNG')
        admin = Client()
        admin.force_login(self.owner)
        response = admin.post('/admin/admin_panel/shopproduct/add/', {
            'title': 'Товар с фото', 'price_som': 100, 'price_coins': 50, 'stock': 0,
            'is_active': 'on', 'order': 3, 'image': SimpleUploadedFile('product.png', png.getvalue(), 'image/png'),
            '_save': 'Сохранить',
        })
        self.assertEqual(response.status_code, 302)
        item = ShopProduct.objects.get(title='Товар с фото')
        self.assertTrue(item.image_url.startswith('/api/v1/media/'))
        image = self.api.get(item.image_url)
        self.assertEqual((image.status_code, image['Content-Type']), (200, 'image/webp'))

    def test_install_preserves_stock_and_deploy_preserves_edits(self):
        with connection.schema_editor() as editor:
            editor.delete_model(ShopOrder)
            editor.delete_model(ShopProduct)
        call_command('install_shop', stdout=StringIO())
        zeiss = ShopProduct.objects.get(title='Оригинальная салфетка Zeiss')
        self.assertEqual((zeiss.price_coins, zeiss.stock), (60, 10))
        zeiss.stock = 3
        zeiss.price_coins = 99
        zeiss.is_active = False
        zeiss.save()
        call_command('install_shop', missing_only=True, stdout=StringIO())
        zeiss.refresh_from_db()
        self.assertEqual((zeiss.price_coins, zeiss.stock, zeiss.is_active), (99, 3, False))
        call_command('install_shop', stdout=StringIO())
        zeiss.refresh_from_db()
        self.assertEqual((zeiss.price_coins, zeiss.stock, zeiss.is_active), (60, 3, False))
        self.assertEqual(ShopProduct.objects.filter(item_type='PHYSICAL').count(), 12)
        self.assertEqual(ShopProduct.objects.count(), 18)
        ShopProduct.objects.exclude(pk=zeiss.pk).update(stock=0)
        call_command('install_shop', missing_only=True, restock_empty=True, stdout=StringIO())
        self.assertEqual(ShopProduct.objects.filter(stock=10).count(), 11)
        self.assertEqual(ShopProduct.objects.filter(stock=999).count(), 6)
        zeiss.refresh_from_db()
        self.assertEqual(zeiss.stock, 3)
