import asyncio
import unittest

import apps.base.views as views
from apps.base.views import normalize_share_code


class FakeFileCodes:
    seen_code = None

    @classmethod
    def filter(cls, **kwargs):
        cls.seen_code = kwargs.get("code")
        return cls()

    async def first(self):
        return None


class RetrieveCodeTests(unittest.TestCase):
    def test_normalize_share_code_strips_surrounding_whitespace(self):
        self.assertEqual(normalize_share_code(" 12345\n"), "12345")

    def test_get_code_file_by_code_queries_normalized_code(self):
        original_file_codes = views.FileCodes
        views.FileCodes = FakeFileCodes
        try:
            has_file, message = asyncio.run(views.get_code_file_by_code(" 12345\n"))
        finally:
            views.FileCodes = original_file_codes

        self.assertFalse(has_file)
        self.assertEqual(message, "文件不存在")
        self.assertEqual(FakeFileCodes.seen_code, "12345")
