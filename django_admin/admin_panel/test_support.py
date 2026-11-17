from django.db import connection
from admin_panel.models import *

UNMANAGED_MODELS = [StudyGroup, User, Lesson, Task, Submission, ScoreAdjustment, Achievement,
                    UserAchievement, MonthlyScoreArchive, MediaAsset, Session, SubscriptionGrant,
                    TelegramIdentity, PasswordResetTicket, AuthRateBucket, TelegramUpdate, TelegramOutbox]


def create_schema():
    with connection.schema_editor() as editor:
        for model in UNMANAGED_MODELS:
            if model._meta.db_table not in connection.introspection.table_names():
                editor.create_model(model)


def clear_data():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            tables = ','.join(connection.ops.quote_name(m._meta.db_table) for m in UNMANAGED_MODELS)
            cursor.execute('TRUNCATE ' + tables + ' CASCADE')
        else:
            with connection.constraint_checks_disabled():
                for model in reversed(UNMANAGED_MODELS):
                    cursor.execute('DELETE FROM ' + connection.ops.quote_name(model._meta.db_table))


def subscribe(user):
    group, _ = StudyGroup.objects.get_or_create(name=user.group_number or 'js-01')
    SubscriptionGrant.objects.get_or_create(user=user, defaults={'telegram_username': 't_' + user.pk.replace('-', '')[:30], 'group': group, 'granted_by': 'test'})
    return user


def create_user(**kwargs):
    user = User.objects.create(**kwargs)
    if kwargs.get('has_subscription'):
        subscribe(user)
    return user
