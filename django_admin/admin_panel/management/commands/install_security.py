from contextlib import nullcontext
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import Count
from admin_panel.models import (ScoreAdjustment, Submission, Session, AuthRateBucket, TelegramUpdate, TelegramOutbox, TelegramIdentity)
from admin_panel.authentication import refresh_digest


class Command(BaseCommand):
    help = 'Install additive security schema and hash legacy refresh tokens. No user records removed.'

    def handle(self, *args, **options):
        call_command('install_subscriptions', stdout=self.stdout)
        duplicate = Submission.objects.values('user_id', 'task_id', 'version').annotate(n=Count('id')).filter(n__gt=1).exists()
        if duplicate:
            raise CommandError('Duplicate attempt versions exist. Resolve before adding uniqueness; no changes applied.')
        with (transaction.atomic() if connection.vendor == 'postgresql' else nullcontext()):
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('merts.install_security'))")
            with connection.schema_editor(atomic=(connection.vendor != 'postgresql')) as editor:
                with connection.cursor() as cursor:
                    cols = {c.name for c in connection.introspection.get_table_description(cursor, 'ScoreAdjustment')}
                    sub_cols = {c.name for c in connection.introspection.get_table_description(cursor, 'Submission')}
                    constraints = connection.introspection.get_constraints(cursor, 'Submission')
                if 'idempotency_key' not in cols:
                    editor.add_field(ScoreAdjustment, ScoreAdjustment._meta.get_field('idempotency_key'))
                if 'was_revised' not in sub_cols:
                    editor.add_field(Submission, Submission._meta.get_field('was_revised'))
                if 'submission_attempt_unique' not in constraints:
                    editor.add_constraint(Submission, Submission._meta.constraints[0])
                with connection.cursor() as cursor:
                    columns = {c.name: c for c in connection.introspection.get_table_description(cursor, 'TelegramIdentity')}
                if not columns['username'].null_ok:
                    field = TelegramIdentity._meta.get_field('username')
                    old_field = field.clone()
                    old_field.set_attributes_from_name('username')
                    old_field.model = TelegramIdentity
                    old_field.null = False
                    editor.alter_field(TelegramIdentity, old_field, field)
                tables = connection.introspection.table_names()
                for model in (AuthRateBucket, TelegramUpdate, TelegramOutbox):
                    if model._meta.db_table not in tables:
                        editor.create_model(model)
                if connection.vendor == 'postgresql':
                    with connection.cursor() as cursor:
                        cursor.execute('CREATE INDEX IF NOT EXISTS "idx_tg_outbox_status_avail" ON "TelegramOutbox" ("status", "available_at")')
                        if not Submission.objects.filter(status__in=('SENT', 'IN_REVIEW')).values('user_id', 'task_id').annotate(n=Count('id')).filter(n__gt=1).exists():
                            cursor.execute(
                                'CREATE UNIQUE INDEX IF NOT EXISTS "submission_active_unique" '
                                'ON "Submission" ("user_id", "task_id") WHERE status IN (\'SENT\', \'IN_REVIEW\')'
                            )
                        if not Submission.objects.filter(status='ACCEPTED').values('user_id', 'task_id').annotate(n=Count('id')).filter(n__gt=1).exists():
                            cursor.execute(
                                'CREATE UNIQUE INDEX IF NOT EXISTS "submission_accepted_unique" '
                                'ON "Submission" ("user_id", "task_id") WHERE status = \'ACCEPTED\''
                            )
        with transaction.atomic():
            # Old refresh values were 64-character lowercase hex; hash tagging distinguishes them.
            for session in Session.objects.select_for_update().exclude(refresh_token__startswith='sha256:'):
                session.refresh_token = refresh_digest(session.refresh_token)
                session.save(update_fields=['refresh_token'])
        self.stdout.write(self.style.SUCCESS('Security schema installed.'))
