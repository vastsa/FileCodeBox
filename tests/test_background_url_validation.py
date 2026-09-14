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


if __name__ == "__main__":
    unittest.main()
