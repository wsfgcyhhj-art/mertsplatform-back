from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from admin_panel.models import RoleChoices, ShopOrder, ShopOrderStatus, ShopProduct, SubmissionStatusChoices, User
from admin_panel.services.telegram_service import escape_html, send_async_notification


def shop_balance(user):
    homework = user.submissions.filter(status=SubmissionStatusChoices.ACCEPTED).aggregate(total=Sum('score', default=0))
    achievements = user.user_achievements.aggregate(total=Sum('achievement__points', default=0))
    adjustments = user.score_adjustments.aggregate(total=Sum('amount', default=0))
    earned = homework['total'] + achievements['total'] + user.streak_count * 5 + adjustments['total']
    spent = user.shop_orders.filter(
        status__in=(ShopOrderStatus.PENDING, ShopOrderStatus.COMPLETED)
    ).aggregate(total=Sum('price_coins', default=0))['total']
    return {'totalEarnedPoints': earned, 'spentPoints': spent, 'availableCoins': max(0, earned - spent)}


class ShopConflict(Exception):
    pass


@transaction.atomic
def place_order(user, product_id, comment, request_key=None, expected_price=None):
    user = User.objects.select_for_update().get(pk=user.pk)
    order_id = str(uuid5(NAMESPACE_URL, f'merts.shop:{user.pk}:{request_key}')) if request_key else None
    if order_id:
        previous = ShopOrder.objects.filter(pk=order_id, user=user).select_related('product').first()
        if previous:
            if previous.product_id != product_id or previous.comment != comment:
                raise ShopConflict('Этот ключ уже использован для другого заказа.')
            return previous, shop_balance(user), False

    product = ShopProduct.objects.select_for_update().get(pk=product_id, is_active=True)
    if expected_price is not None and expected_price != product.price_coins:
        raise ShopConflict('Цена изменилась. Обновите каталог перед покупкой.')
    if product.stock == 0:
        raise ShopConflict('Товар закончился.')
    balance = shop_balance(user)
    if balance['availableCoins'] < product.price_coins:
        raise ShopConflict('Недостаточно баллов для покупки.')

    order = ShopOrder(user=user, product=product, price_coins=product.price_coins, comment=comment)
    if order_id:
        order.pk = order_id
    order.save(force_insert=True)
    product.stock -= 1
    product.save(update_fields=['stock'])

    title = escape_html(product.title)
    send_async_notification(
        user.pk, f'🛍 <b>Заказ оформлен!</b> Товар: <b>{title}</b> за <b>{order.price_coins} баллов</b>. '
        'Ожидайте подтверждения выдачи.',
    )
    admins = User.objects.filter(role=RoleChoices.ADMIN, telegram_chat_id__isnull=False).exclude(telegram_chat_id='')
    owner = admins.filter(pk=settings.PLATFORM_OWNER_USER_ID).first()
    recipients = [owner.pk] if owner else admins.values_list('pk', flat=True)
    for recipient in recipients:
        if recipient != user.pk:
            send_async_notification(
                recipient,
                f'🛍 <b>Новый заказ мерча</b>\n{title} — {order.price_coins} баллов.\n'
                f'Студент: @{escape_html(user.login)}\nЗаказ: <code>{order.pk}</code>',
            )
    balance['spentPoints'] += order.price_coins
    balance['availableCoins'] -= order.price_coins
    return order, balance, True


@transaction.atomic
def process_order(order_id, status, operator):
    if status not in (ShopOrderStatus.COMPLETED, ShopOrderStatus.CANCELLED):
        raise ValueError('Invalid shop order transition')
    user_id = ShopOrder.objects.values_list('user_id', flat=True).get(pk=order_id)
    User.objects.select_for_update().get(pk=user_id)
    order = ShopOrder.objects.select_for_update().get(pk=order_id)
    if order.status != ShopOrderStatus.PENDING:
        return False

    order.status = status
    order.processed_by = operator.get_username()
    order.processed_at = timezone.now()
    order.save(update_fields=['status', 'processed_by', 'processed_at'])
    if status == ShopOrderStatus.CANCELLED:
        product = ShopProduct.objects.select_for_update().get(pk=order.product_id)
        product.stock += 1
        product.save(update_fields=['stock'])
    else:
        send_async_notification(
            order.user_id,
            f'🎉 <b>Ваш мерч готов к выдаче!</b> Вы можете забрать <b>{escape_html(order.product.title)}</b>.',
        )
    return True
