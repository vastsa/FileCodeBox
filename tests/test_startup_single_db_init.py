"""One Tortoise init path; ORM exception mappings still registered."""
import asyncio
import unittest
from pathlib import Path
from unittest import mock

from tortoise.exceptions import DoesNotExist, IntegrityError

import main


async def _idle_task():
    # Stand-in for the real background loops; the lifespan cancels it on exit.
    await asyncio.sleep(3600)


class StartupSingleInitTests(unittest.TestCase):
    def test_orm_exception_handlers_are_registered(self):
        # Behavior pinned by test_admin_write_paths: DoesNotExist -> 404 JSON.
        # IntegrityError -> 422 must stay available too.
        self.assertIn(DoesNotExist, main.app.exception_handlers)
        self.assertIn(IntegrityError, main.app.exception_handlers)

    def test_register_tortoise_is_not_used(self):
        # register_tortoise merges another lifespan that calls Tortoise.init
        # before init_db(); batch 4 (SQLite PRAGMAs) needs a single init path.
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertNotIn("import register_tortoise", source)
        self.assertNotIn("register_tortoise(", source)

    def test_lifespan_does_not_initialize_tortoise_outside_init_db(self):
        async def scenario():
            init_db_calls = []

            async def fake_init_db():
                init_db_calls.append(True)

            async def fake_load_config():
                return None

            with (
                mock.patch.object(main, "init_db", fake_init_db),
                mock.patch.object(main, "load_config", fake_load_config),
                mock.patch.object(main, "delete_expire_files", _idle_task),
                mock.patch.object(main, "clean_incomplete_uploads", _idle_task),
                mock.patch.object(
                    main, "clean_expired_presign_sessions", _idle_task
                ),
                mock.patch.object(main.Tortoise, "init") as tortoise_init,
                mock.patch.object(
                    main.Tortoise, "close_connections"
                ),
            ):
                # FastAPI merges the lifespan of every included router, so use
                # the installed context rather than main.lifespan directly.
                async with main.app.router.lifespan_context(main.app):
                    pass

            return init_db_calls, tortoise_init

        init_db_calls, tortoise_init = asyncio.run(scenario())

        self.assertEqual(init_db_calls, [True])
        tortoise_init.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
