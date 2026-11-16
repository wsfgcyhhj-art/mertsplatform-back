from django.core.management.base import BaseCommand
from admin_panel.services.telegram_service import run_telegram_polling


class Command(BaseCommand):
    help = 'Runs Telegram Bot in long-polling mode for local development and Docker'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Telegram Bot polling daemon...'))
        try:
            run_telegram_polling()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Polling stopped by user.'))
