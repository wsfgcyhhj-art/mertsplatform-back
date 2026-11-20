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
        self.stdout.write(self.style.SUCCESS(f'Base schema ready (created {created} tables).'))
