import signal
import time
from django.conf import settings
from django.core.management.base import BaseCommand
from admin_panel.services.telegram_service import (
    get_bot_token,
    run_telegram_polling,
    setup_telegram_bot_menu,
)


class Command(BaseCommand):
    help = 'Runs Telegram Bot in long-polling mode for local development and Docker'

    def handle(self, *args, **options):
        if getattr(settings, 'TELEGRAM_MODE', 'polling') != 'polling' or not get_bot_token():
            self.stdout.write(self.style.WARNING('Telegram polling disabled or token missing; idling until signal.'))
            idle = True

            def _stop(_signum, _frame):
                nonlocal idle
                idle = False

            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    signal.signal(sig, _stop)
                except ValueError:
                    pass
            while idle:
                time.sleep(60)
            return

        self.stdout.write(self.style.SUCCESS('Starting Telegram Bot polling daemon...'))
        try:
            run_telegram_polling()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Polling stopped by user.'))
