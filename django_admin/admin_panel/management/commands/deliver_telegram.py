import time
from django.core.management.base import BaseCommand
from admin_panel.services.outbox_service import drain

class Command(BaseCommand):
    help = 'Deliver durable Telegram messages; run as a dedicated Render worker.'
    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
    def handle(self, *args, **options):
        while True:
            self.stdout.write(f'Delivered: {drain()}')
            if options['once']:
                break
            time.sleep(5)
