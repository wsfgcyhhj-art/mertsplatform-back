from django.apps import AppConfig

class AdminPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_panel'
    verbose_name = 'MertsPlatform — Управление платформой'

    def ready(self):
        import admin_panel.signals  # noqa
        import admin_panel.extensions  # noqa
