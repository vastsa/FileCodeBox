"""Shared test helpers: settings-override mixin and in-memory Tortoise setup.

Kept unittest-friendly (the legacy suite is unittest-based); pytest fixtures
live in conftest.py and build on top of these helpers.
"""
from tortoise import Tortoise

from core.settings import settings

# Mirrors core.database.get_db_config() but with an in-memory SQLite database
# and no WAL/startup-lock specifics, so tests never touch the real data dir's DB.
MEMORY_DB_CONFIG = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.sqlite",
            "credentials": {"file_path": ":memory:"},
        }
    },
    "apps": {
        "models": {
            "models": ["apps.base.models"],
            "default_connection": "default",
        }
    },
    "use_tz": False,
    "timezone": "Asia/Shanghai",
}


class SettingsOverrideMixin:
    """Snapshot settings.user_config in setUp and restore it in tearDown."""

    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


async def init_memory_db():
    """Init Tortoise against an in-memory DB and create all schemas."""
    # 每个测试都是全新 DB，必须同步失效进程级配置 TTL 缓存，
    # 否则上一个测试的缓存会让 middleware 误判初始化状态。
    import apps.base.config as config_module

    config_module._config_cached_until = 0.0
    await Tortoise.init(config=MEMORY_DB_CONFIG)
    await Tortoise.generate_schemas()


async def close_db():
    await Tortoise.close_connections()
