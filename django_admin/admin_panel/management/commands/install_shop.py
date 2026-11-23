from django.core.management.base import BaseCommand
from django.db import connection, transaction

from admin_panel.models import ShopOrder, ShopProduct


INITIAL_STOCK = 10

CATALOG = (
    ('Оригинальная салфетка Zeiss', 150, 60, 'Мягкая и бережная очистка для очков, линз и экранов без царапин. Чистота и защита ваших устройств каждый день.'),
    ('Мышка проводная INPHIC B1', 700, 250, 'Точная и надёжная для работы и игр. Компактный дизайн и удобное управление каждый день. Доступна в стильном чёрном цвете.'),
    ('Коврик из эко-кожи 40 × 80 см', 800, 280, 'Стильный и компактный, цвет Starry Black. Идеален для работы за столом, защиты поверхности и комфортного письма.'),
    ('Футболка Geeks', 1000, 350, 'Фирменный мерч Geeks'),
    ('Мышка беспроводная ACER OMR218', 1000, 350, 'Стильная и удобная — работает точно и без проводов! Идеальна для офиса, дома и учёбы. Доступна в чёрно-сером цвете.'),
    ('Коврик RGB 80 × 30 или 80 × 40', 1400, 480, 'Стильный коврик с яркой подсветкой и разными рисунками на выбор. Плавное скольжение мыши, защита стола и крутой вид рабочего места!'),
    ('Термокружка Geeks', 1500, 520, 'Фирменный мерч Geeks'),
    ('Черный RGB коврик (90×40)', 1600, 550, 'Большой коврик с яркой RGB-подсветкой, мягкой тканевой поверхностью и прорезиненным основанием. Подключается через USB, несколько режимов подсветки.'),
    ('Подставка для ноутбука HASEE', 1800, 620, 'Железный каркас и регулировка на 360° — настрой под себя! Надёжная, устойчивая и удобная для работы, учёбы и отдыха.'),
    ('Худи Geeks', 2000, 700, 'Фирменный мерч Geeks'),
    ('Повербанк UGREEN 20 000 mAh', 2600, 900, 'Заряди всё и сразу! Высокая ёмкость, быстрая зарядка и стильный дизайн для активных людей.'),
    ('Наушники 1More SonoFlow HC905S', 4700, 1500, 'Беспроводной звук премиум-класса и комфорт для долгого прослушивания. Доступны в стильном чёрном цвете.'),
)


class Command(BaseCommand):
    help = 'Create the unmanaged shop tables and seed the merchandise catalog.'

    def add_arguments(self, parser):
        parser.add_argument('--missing-only', action='store_true', help='Preserve all existing catalog edits.')
        parser.add_argument('--restock-empty', action='store_true', help='Restock empty seeded products.')

    def handle(self, *args, **options):
        with connection.schema_editor() as editor, transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext('merts.install_shop'))")
            tables = connection.introspection.table_names()
            for model in (ShopProduct, ShopOrder):
                if model._meta.db_table not in tables:
                    editor.create_model(model)
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('CREATE INDEX IF NOT EXISTS "idx_shop_order_user_status" ON "ShopOrder" ("user_id", "status")')
                    cursor.execute('CREATE INDEX IF NOT EXISTS "idx_shop_order_product_id" ON "ShopOrder" ("product_id")')

            for order, (title, price_som, price_coins, description) in enumerate(CATALOG, 1):
                defaults = {
                    'price_som': price_som, 'price_coins': price_coins,
                    'description': description, 'order': order,
                }
                create_defaults = {**defaults, 'stock': INITIAL_STOCK}
                if options['missing_only']:
                    ShopProduct.objects.get_or_create(title=title, defaults=create_defaults)
                else:
                    ShopProduct.objects.update_or_create(title=title, defaults=defaults, create_defaults=create_defaults)
            if options['restock_empty']:
                count = ShopProduct.objects.filter(title__in=[item[0] for item in CATALOG], stock=0).update(stock=INITIAL_STOCK)
                self.stdout.write(f'Empty catalog products restocked: {count}.')
        self.stdout.write(self.style.SUCCESS(f'Shop catalog installed ({len(CATALOG)} products).'))
