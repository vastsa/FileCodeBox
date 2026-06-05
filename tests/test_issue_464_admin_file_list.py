import asyncio
import unittest
from datetime import datetime, timedelta

from apps.admin.services import FileService
from core.settings import settings


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


class FakeFileCode:
    def __init__(self):
        self.id = 1
        self.code = "ABC123"
        self.prefix = "report"
        self.suffix = ".txt"
        self.uuid_file_name = "report.txt"
        self.file_path = "share/data/2026/01/01/abc"
        self.size = 12
        self.text = None
        self.expired_at = datetime(2026, 1, 2, 12, 0, 0)
        self.expired_count = 3
        self.used_count = 0
        self.created_at = datetime(2026, 1, 1, 12, 0, 0)
        self.file_hash = "a" * 64
        self.is_chunked = False
        self.upload_id = None

    async def is_expired(self):
        return False


class AdminFileItemTests(SettingsOverrideMixin, unittest.TestCase):
    def test_build_admin_file_item_serializes_required_fields(self):
        settings.file_storage = "local"
        service = FileService()
        now = datetime(2026, 1, 1, 13, 0, 0)

        item = asyncio.run(service._build_admin_file_item(FakeFileCode(), now=now))

        self.assertEqual(item["id"], 1)
        self.assertEqual(item["name"], "report.txt")
        self.assertEqual(item["type"], "file")
        self.assertFalse(item["isExpired"])
        self.assertEqual(item["remainingDownloads"], 3)
        self.assertEqual(item["file_path"], "share/data/2026/01/01/abc")
        self.assertIn("never_retrieved", item["statusInsights"]["reasons"])
        self.assertEqual(item["statusInsights"]["metrics"]["ageSeconds"], 3600)

    def test_build_admin_file_item_marks_expiring_soon(self):
        settings.file_storage = "local"
        service = FileService()
        file_code = FakeFileCode()
        now = file_code.expired_at - timedelta(hours=2)

        item = asyncio.run(service._build_admin_file_item(file_code, now=now))

        self.assertEqual(item["statusInsights"]["severity"], "warning")
        self.assertIn("expires_soon", item["statusInsights"]["reasons"])
