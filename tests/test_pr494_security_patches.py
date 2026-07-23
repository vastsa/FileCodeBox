import asyncio
import hashlib
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from tortoise import Tortoise

from apps.base import views
from apps.base.models import FileCodes
from apps.base.quota import _detect_sql_dialect, _sql_placeholders, reserve_storage
from apps.base.utils import validate_expire_style
from core.settings import settings
from core.utils import get_select_token


class FakeStorage:
    async def get_file_url(self, file_code):
        return f"https://example.invalid/{file_code.code}"

    async def get_file_response(self, file_code):
        return {"downloaded": file_code.code}


class SecurityPatchTests(unittest.TestCase):
    def test_validate_expire_style_rejects_unknown_mode(self):
        original = dict(settings.user_config)
        try:
            settings.expireStyle = ["day", "count"]
            self.assertEqual(validate_expire_style("day"), "day")
            with self.assertRaises(HTTPException) as ctx:
                validate_expire_style("forever")
            self.assertEqual(ctx.exception.status_code, 400)
        finally:
            settings.user_config = original

    def test_sql_placeholders_follow_dialect(self):
        asyncio.run(self._assert_sql_placeholders())

    async def _assert_sql_placeholders(self):
        await Tortoise.init(
            config={
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
        )
        try:
            self.assertEqual(_detect_sql_dialect(), "sqlite")
            self.assertEqual(_sql_placeholders(3), ["?", "?", "?"])

            with patch(
                "apps.base.quota._detect_sql_dialect", return_value="postgres"
            ):
                self.assertEqual(_sql_placeholders(3), ["$1", "$2", "$3"])
            with patch("apps.base.quota._detect_sql_dialect", return_value="mysql"):
                self.assertEqual(_sql_placeholders(2), ["%s", "%s"])

            # sqlite 下 reserve_storage 仍可正常工作
            settings.storageLimit = 100
            await Tortoise.generate_schemas()
            await reserve_storage("patch-token", 10, 300)
        finally:
            settings.storageLimit = 0
            await Tortoise.close_connections()

    def test_download_token_accepts_previous_window(self):
        asyncio.run(self._assert_download_token_window())

    async def _assert_download_token_window(self):
        original = dict(settings.user_config)
        settings.jwt_secret = "test-secret-key-for-token-window"
        now = 2_000_500  # 落在窗口 2000 内
        code = "ABCDE"
        with patch("core.utils.time.time", return_value=now):
            current = await get_select_token(code, offset=0)
            previous = await get_select_token(code, offset=1)

        expected_current = hashlib.sha256(
            f"{code}{int(now / 1000)}000{settings.jwt_secret}".encode()
        ).hexdigest()
        expected_previous = hashlib.sha256(
            f"{code}{int(now / 1000) - 1}000{settings.jwt_secret}".encode()
        ).hexdigest()
        self.assertEqual(current, expected_current)
        self.assertEqual(previous, expected_previous)

        await Tortoise.init(
            config={
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
        )
        await Tortoise.generate_schemas()
        try:
            await FileCodes.create(
                code=code,
                prefix="demo",
                suffix=".txt",
                expired_count=-1,
                size=1,
            )
            # 模拟请求进入下一窗口，但仍携带上一窗口 token
            next_window = now + 1000
            with patch("core.utils.time.time", return_value=next_window):
                with patch.dict(views.storages, {"local": FakeStorage}):
                    result = await views.download_file(
                        key=current, code=code, ip="127.0.0.1"
                    )
            self.assertEqual(result, {"downloaded": code})
        finally:
            settings.user_config = original
            await Tortoise.close_connections()


if __name__ == "__main__":
    unittest.main()
