"""Tests for the background-URL config validation.

Themes inject the site ``background`` config into inline CSS ``url('...')``;
a single-quote breakout there is not neutralized by html escaping (the CSS
engine decodes entities back). The fix is upstream validation at config-write
time: only well-formed http(s) URLs (or empty) may be stored.
"""
import asyncio
import unittest

from tests.helpers import SettingsOverrideMixin, close_db, init_memory_db

from apps.admin.services import ConfigService
from core.utils import validate_background_url

VALID = [
    "",
    "https://example.com/bg.webp",
    "http://cdn.example.org/a/b.jpg?id=1&token=ab",
]
INVALID = [
    "x') ;background:url(https://evil.com/)",
    "https://example.com/bg') ;background:url(evil)",
    "javascript:alert(1)",
    "data:image/svg+xml;base64,AAAA",
    "/relative/path.jpg",
    "//protocol-relative.example/bg",
    "https://example.com/a b.png",
    "https://example.com/a(b).png",
]


class ValidateBackgroundUrlTests(unittest.TestCase):
    def test_valid_values_pass_through(self):
        for value in VALID:
            self.assertEqual(validate_background_url(value), value.strip() if value else "")

    def test_injection_and_non_http_values_rejected(self):
        for value in INVALID:
            with self.assertRaises(ValueError, msg=value):
                validate_background_url(value)

    def test_none_and_whitespace_become_empty(self):
        self.assertEqual(validate_background_url(None), "")
        self.assertEqual(validate_background_url("   "), "")


class ConfigServiceBackgroundGuardTests(SettingsOverrideMixin, unittest.TestCase):
    def test_update_config_rejects_malicious_background(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        await init_memory_db()
        try:
            service = ConfigService()
            # 合法值可通过
            await service.update_config({"background": "https://ok.example/bg.png"})
            # 恶意值被拒且不落库
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                await service.update_config({"background": "x') ;background:url(https://evil.com/)"})
            self.assertEqual(ctx.exception.status_code, 400)

            from apps.base.models import KeyValue

            record = await KeyValue.filter(key="settings").first()
            self.assertEqual(
                record.value.get("background"), "https://ok.example/bg.png",
                "被拒绝的值不得写入配置",
            )
        finally:
            await close_db()


class LegacyBackgroundUpgradeTests(SettingsOverrideMixin, unittest.TestCase):
    """存量部署升级：旧版本合法、新校验不接受的值，不得阻塞设置保存。"""

    def test_unchanged_legacy_background_does_not_block_unrelated_save(self):
        asyncio.run(self._unchanged_legacy_allows_save())

    async def _unchanged_legacy_allows_save(self):
        await init_memory_db()
        try:
            from apps.base.config import refresh_settings
            from apps.base.models import KeyValue

            # 旧版本合法（相对路径 + 空格），新的 http(s) 校验会拒绝
            legacy = "/static/bg image.png"
            await KeyValue.create(
                key="settings", value={"background": legacy, "name": "old"}
            )
            await refresh_settings(force=True)

            service = ConfigService()
            # 修复前这里会 400，导致存量部署连无关设置项都保存不了
            await service.update_config({"name": "new"})

            record = await KeyValue.filter(key="settings").first()
            self.assertEqual(record.value.get("background"), legacy, "旧值应原样保留")
            self.assertEqual(record.value.get("name"), "new")
        finally:
            await close_db()

    def test_changing_background_is_still_validated(self):
        asyncio.run(self._change_still_validated())

    async def _change_still_validated(self):
        await init_memory_db()
        try:
            from fastapi import HTTPException

            from apps.base.config import refresh_settings
            from apps.base.models import KeyValue

            await KeyValue.create(key="settings", value={"background": "/legacy/bg.png"})
            await refresh_settings(force=True)

            service = ConfigService()
            # 修改为恶意值仍然被拒
            with self.assertRaises(HTTPException) as ctx:
                await service.update_config(
                    {"background": "x') ;background:url(https://evil.com/)"}
                )
            self.assertEqual(ctx.exception.status_code, 400)
            # 修改为合法值可以通过
            await service.update_config({"background": "https://ok.example/bg.png"})
            record = await KeyValue.filter(key="settings").first()
            self.assertEqual(record.value.get("background"), "https://ok.example/bg.png")
        finally:
            await close_db()


if __name__ == "__main__":
    unittest.main()
