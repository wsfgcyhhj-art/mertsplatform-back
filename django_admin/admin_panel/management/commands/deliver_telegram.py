import logging
import signal
import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from admin_panel.services.outbox_service import drain

logger = logging.getLogger('telegram_service')


class Command(BaseCommand):
    help = 'Deliver durable Telegram outbox messages.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--interval', type=float, default=2.0)

    def handle(self, *args, **options):
        interval = max(0.5, float(options['interval']))
        running = True

        def _stop(_signum, _frame):
            nonlocal running
            running = False

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _stop)
            except ValueError:
                pass

        while running:
            close_old_connections()
            try:
                delivered = drain()
                if delivered or options['once']:
                    self.stdout.write(f'Delivered: {delivered}')
            except Exception as exc:
                logger.exception('Telegram outbox drain failed: %s', type(exc).__name__)
            if options['once'] or not running:
                break
            time.sleep(interval)
