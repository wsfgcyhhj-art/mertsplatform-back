from contextlib import nullcontext
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from admin_panel.models import User, StudyGroup, SubscriptionGrant, TelegramIdentity, PasswordResetTicket


class Command(BaseCommand):
    help = "Ensure study group and compatibility user columns exist with open platform access."

    def handle(self, *args, **options):
        # Unmanaged models are not created by migrate.
        with (transaction.atomic() if connection.vendor == 'postgresql' else nullcontext()):
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('merts.install_subscriptions'))")
                    cursor.execute('''CREATE TABLE IF NOT EXISTS "StudyGroup" (
                        "id" varchar(64) PRIMARY KEY, "name" varchar(64) UNIQUE NOT NULL,
                        "month" integer NOT NULL DEFAULT 1,
                        "created_at" timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        "is_active" boolean NOT NULL DEFAULT true)''')
                    cursor.execute('ALTER TABLE "StudyGroup" ADD COLUMN IF NOT EXISTS "is_active" boolean NOT NULL DEFAULT true')
            elif StudyGroup._meta.db_table not in connection.introspection.table_names():
                with connection.schema_editor(atomic=(connection.vendor != 'postgresql')) as editor:
                    editor.create_model(StudyGroup)
            with connection.cursor() as cursor:
                columns = {c.name for c in connection.introspection.get_table_description(cursor, User._meta.db_table)}
            with connection.schema_editor(atomic=(connection.vendor != 'postgresql')) as editor:
                for name in ('has_subscription', 'subscription_expires_at', 'must_change_password', 'password_uses_sha256'):
                    if name not in columns:
                        editor.add_field(User, User._meta.get_field(name))
                with connection.cursor() as cursor:
                    group_columns = {c.name for c in connection.introspection.get_table_description(cursor, StudyGroup._meta.db_table)}
                if 'is_active' not in group_columns:
                    editor.add_field(StudyGroup, StudyGroup._meta.get_field('is_active'))
                tables = connection.introspection.table_names()
                for model in (SubscriptionGrant, TelegramIdentity, PasswordResetTicket):
                    if model._meta.db_table not in tables:
                        editor.create_model(model)
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('ALTER TABLE "User" ALTER COLUMN "has_subscription" SET DEFAULT true')
                    cursor.execute('CREATE INDEX IF NOT EXISTS "idx_subgrant_group_id" ON "SubscriptionGrant" ("group_id")')
                    cursor.execute('CREATE INDEX IF NOT EXISTS "idx_pwreset_user_id" ON "PasswordResetTicket" ("user_id")')
            User.objects.filter(has_subscription=False).update(has_subscription=True)
            names = set(User.objects.exclude(group_number__isnull=True).exclude(group_number='').values_list('group_number', flat=True))
            from admin_panel.services.group_service import parse_month_from_group_name
            for name in names:
                if name.upper() == 'ALL':
                    continue
                group, _ = StudyGroup.objects.get_or_create(name=name, defaults={'month': parse_month_from_group_name(name), 'is_active': True})
                User.objects.filter(group_number=name, study_group__isnull=True).update(study_group=group)
        self.stdout.write(self.style.SUCCESS('Open access schema ensured; all users have active access.'))
