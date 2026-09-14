from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _set_sqlite_pragmas(sender, connection, **kwargs):
    """SQLite 部署/测试时启用 WAL 与 busy_timeout，降低并发写冲突。"""
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")


class SerialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "serials"
    verbose_name = "连续出版物登记"

    def ready(self):
        connection_created.connect(_set_sqlite_pragmas)
