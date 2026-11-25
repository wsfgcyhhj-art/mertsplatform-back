from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from admin_panel.models import (
    RoleChoices,
    ShopItemTypeChoices,
    ShopOrder,
    ShopOrderStatus,
    ShopProduct,
    SubmissionStatusChoices,
    User,
)
from admin_panel.services.score_service import latest_accepted
from admin_panel.services.telegram_service import escape_html, send_async_notification


def shop_balance(user):
    homework = latest_accepted(user.submissions.all()).aggregate(total=Sum('score', default=0))
    achievements = user.user_achievements.aggregate(total=Sum('achievement__points', default=0))
    adjustments = user.score_adjustments.aggregate(total=Sum('amount', default=0))
    earned = homework['total'] + achievements['total'] + adjustments['total']
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
    if product.stock <= 0:
        raise ShopConflict('Товар закончился.')
    balance = shop_balance(user)
    if balance['availableCoins'] < product.price_coins:
        raise ShopConflict('Недостаточно баллов для покупки.')

    is_digital = product.item_type != ShopItemTypeChoices.PHYSICAL
    frame_slug = ''
    if product.item_type == ShopItemTypeChoices.AVATAR_FRAME:
        meta = product.metadata if isinstance(product.metadata, dict) else {}
        frame_slug = str(meta.get('frameSlug') or '').strip().lower()
        if not frame_slug:
            raise ShopConflict('Некорректные метаданные рамки аватара.')
        raw_unlocked = user.unlocked_avatar_frames if isinstance(user.unlocked_avatar_frames, list) else []
        unlocked_frames = [str(f).strip().lower() for f in raw_unlocked if isinstance(f, (str, int)) and str(f).strip()]
        if frame_slug in unlocked_frames:
            raise ShopConflict('Эта рамка аватара уже разблокирована.')

    now = timezone.now()
    order = ShopOrder(
        user=user,
        product=product,
        price_coins=product.price_coins,
        comment=comment,
        status=ShopOrderStatus.COMPLETED if is_digital else ShopOrderStatus.PENDING,
        processed_by='system:instant' if is_digital else '',
        processed_at=now if is_digital else None,
    )
    if order_id:
        order.pk = order_id
    order.save(force_insert=True)
    product.stock -= 1
    product.save(update_fields=['stock'])

    title = escape_html(product.title)
    if is_digital:
        if product.item_type == ShopItemTypeChoices.STREAK_FREEZE:
            user.streak_freezes = (user.streak_freezes or 0) + 1
            user.updated_at = now
            user.save(update_fields=['streak_freezes', 'updated_at'])
        elif product.item_type == ShopItemTypeChoices.DEADLINE_EXTEND:
            user.deadline_boosters = (user.deadline_boosters or 0) + 1
            user.updated_at = now
            user.save(update_fields=['deadline_boosters', 'updated_at'])
        elif product.item_type == ShopItemTypeChoices.AVATAR_FRAME:
            raw_unlocked = user.unlocked_avatar_frames if isinstance(user.unlocked_avatar_frames, list) else []
            unlocked_frames = [str(f).strip().lower() for f in raw_unlocked if isinstance(f, (str, int)) and str(f).strip()]
            if frame_slug not in unlocked_frames:
                unlocked_frames.append(frame_slug)
            user.unlocked_avatar_frames = unlocked_frames
            user.updated_at = now
            user.save(update_fields=['unlocked_avatar_frames', 'updated_at'])
        send_async_notification(
            user.pk,
            f'⚡ <b>Цифровой бонус активирован!</b> Начислено: <b>{title}</b> за <b>{order.price_coins} баллов</b>.',
        )
    else:
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
    order = ShopOrder.objects.select_for_update(of=('self',)).select_related('product').get(pk=order_id)
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
        send_async_notification(
            order.user_id,
            f'ℹ️ <b>Заказ отменён.</b> Товар <b>{escape_html(order.product.title)}</b> — '
            f'<b>{order.price_coins} баллов</b> возвращены на ваш баланс.',
        )
    else:
        send_async_notification(
            order.user_id,
            f'🎉 <b>Ваш мерч готов к выдаче!</b> Вы можете забрать <b>{escape_html(order.product.title)}</b>.',
        )
    return True
