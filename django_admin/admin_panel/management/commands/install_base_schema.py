from django.core.management.base import BaseCommand
from django.db import connection, transaction

from admin_panel.models import (
    Achievement,
    Lesson,
    MediaAsset,
    MonthlyScoreArchive,
    ScoreAdjustment,
    Session,
    StudyGroup,
    Submission,
    Task,
    User,
    UserAchievement,
)

BASE_UNMANAGED_MODELS = (
    StudyGroup,
    User,
    Session,
    Lesson,
    Task,
    Submission,
    ScoreAdjustment,
    Achievement,
    UserAchievement,
    MonthlyScoreArchive,
    MediaAsset,
)


class Command(BaseCommand):
    help = 'Create missing base unmanaged tables idempotently for fresh PostgreSQL deployments.'

    def handle(self, *args, **options):
        created = 0
        with connection.schema_editor() as editor, transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('merts.install_base_schema'))")
            existing = set(connection.introspection.table_names())
            for model in BASE_UNMANAGED_MODELS:
                table = model._meta.db_table
                if table not in existing:
                    editor.create_model(model)
                    existing.add(table)
                    created += 1
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    for sql in (
                        'CREATE INDEX IF NOT EXISTS "idx_user_group_id" ON "User" ("group_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_user_mentor_id" ON "User" ("mentor_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_user_group_month" ON "User" ("group_number", "current_month")',
                        'CREATE INDEX IF NOT EXISTS "idx_session_user_id" ON "Session" ("user_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_submission_user_task" ON "Submission" ("user_id", "task_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_submission_task_id" ON "Submission" ("task_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_submission_status_created" ON "Submission" ("status", "created_at")',
                        'CREATE INDEX IF NOT EXISTS "idx_score_adj_user_month" ON "ScoreAdjustment" ("user_id", "month")',
                        'CREATE INDEX IF NOT EXISTS "idx_score_adj_admin_id" ON "ScoreAdjustment" ("admin_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_user_ach_ach_id" ON "UserAchievement" ("achievement_id")',
                        'CREATE INDEX IF NOT EXISTS "idx_media_owner_kind" ON "MediaAsset" ("owner_id", "kind")',
                        '''DO $$
                        DECLARE
                            con_name text;
                        BEGIN
                            SELECT c.conname INTO con_name
                            FROM pg_constraint c
                            JOIN pg_class t ON c.conrelid = t.oid
                            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
                            WHERE t.relname = 'ScoreAdjustment'
                              AND a.attname = 'admin_id'
                              AND c.contype = 'f'
                              AND c.confdeltype = 'c'
                            LIMIT 1;
                            IF con_name IS NOT NULL THEN
                                EXECUTE format('ALTER TABLE "ScoreAdjustment" DROP CONSTRAINT %I', con_name);
                                EXECUTE 'ALTER TABLE "ScoreAdjustment" ADD CONSTRAINT ' || quote_ident(con_name) ||
                                    ' FOREIGN KEY ("admin_id") REFERENCES "User" ("id") ON DELETE RESTRICT';
                            END IF;
                        END $$;''',
                    ):
                        cursor.execute(sql)
        self.stdout.write(self.style.SUCCESS(f'Base schema ready (created {created} tables).'))
