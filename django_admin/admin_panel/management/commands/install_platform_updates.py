from contextlib import nullcontext

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from admin_panel.models import ShopProduct, Submission, Task, TaskDeadlineExtension, User


POSTGRES_ALTER_STATEMENTS = (
    'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "is_active" boolean NOT NULL DEFAULT true',
    'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "streak_freezes" integer NOT NULL DEFAULT 0',
    'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "deadline_boosters" integer NOT NULL DEFAULT 0',
    'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "active_avatar_frame" varchar(64) NULL',
    'ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "unlocked_avatar_frames" jsonb NOT NULL DEFAULT \'[]\'::jsonb',
    'ALTER TABLE "Task" ADD COLUMN IF NOT EXISTS "deadline" timestamptz NULL',
    'ALTER TABLE "Submission" ADD COLUMN IF NOT EXISTS "ai_feedback" text NULL',
    'ALTER TABLE "Submission" ADD COLUMN IF NOT EXISTS "ai_reviewed_at" timestamptz NULL',
    'ALTER TABLE "ShopProduct" ADD COLUMN IF NOT EXISTS "item_type" varchar(32) NOT NULL DEFAULT \'PHYSICAL\'',
    'ALTER TABLE "ShopProduct" ADD COLUMN IF NOT EXISTS "metadata" jsonb NOT NULL DEFAULT \'{}\'::jsonb',
    '''CREATE TABLE IF NOT EXISTS "TaskDeadlineExtension" (
        "id" varchar(64) PRIMARY KEY,
        "user_id" varchar(64) NOT NULL REFERENCES "User" ("id") ON DELETE CASCADE,
        "task_id" varchar(64) NOT NULL REFERENCES "Task" ("id") ON DELETE CASCADE,
        "extended_until" timestamptz NOT NULL,
        "created_at" timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT "task_deadline_ext_user_task_uniq" UNIQUE ("user_id", "task_id")
    )''',
    'CREATE INDEX IF NOT EXISTS "idx_user_role_active" ON "User" ("role", "is_active")',
    'CREATE INDEX IF NOT EXISTS "idx_submission_user_created" ON "Submission" ("user_id", "created_at" DESC)',
    'CREATE INDEX IF NOT EXISTS "idx_deadline_ext_task_id" ON "TaskDeadlineExtension" ("task_id")',
)

MODEL_NEW_FIELDS = (
    (User, ('is_active', 'streak_freezes', 'deadline_boosters', 'active_avatar_frame', 'unlocked_avatar_frames')),
    (Task, ('deadline',)),
    (Submission, ('ai_feedback', 'ai_reviewed_at')),
    (ShopProduct, ('item_type', 'metadata')),
)


class Command(BaseCommand):
    help = 'Idempotently install v2 platform columns and tables on PostgreSQL and SQLite.'

    def handle(self, *args, **options):
        with (transaction.atomic() if connection.vendor == 'postgresql' else nullcontext()):
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('merts.install_platform_updates'))")
                    existing_tables = set(connection.introspection.table_names(cursor))
                with connection.schema_editor(atomic=False) as editor:
                    for model in (User, Task, Submission, ShopProduct):
                        if model._meta.db_table not in existing_tables:
                            editor.create_model(model)
                            existing_tables.add(model._meta.db_table)
                with connection.cursor() as cursor:
                    for sql in POSTGRES_ALTER_STATEMENTS:
                        cursor.execute(sql)
            else:
                with connection.schema_editor(atomic=True) as editor:
                    tables = set(connection.introspection.table_names())
                    for model, field_names in MODEL_NEW_FIELDS:
                        table = model._meta.db_table
                        if table not in tables:
                            editor.create_model(model)
                            tables.add(table)
                            continue
                        with connection.cursor() as cursor:
                            cols = {c.name for c in connection.introspection.get_table_description(cursor, table)}
                        for field_name in field_names:
                            if field_name not in cols:
                                editor.add_field(model, model._meta.get_field(field_name))
                    if TaskDeadlineExtension._meta.db_table not in tables:
                        editor.create_model(TaskDeadlineExtension)
        self.stdout.write(self.style.SUCCESS('Platform update schema installed idempotently.'))
