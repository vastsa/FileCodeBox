import asyncio
import datetime
import unittest
from unittest.mock import patch

from tortoise import Tortoise

from apps.base.models import FileCodes
from apps.base import views
from core.settings import DEFAULT_CONFIG, settings
from core.utils import get_now, get_select_token
from main import build_setup_page, parse_setup_options


class FakeStorage:
    direct_url_calls = 0

    async def get_file_url(self, file_code):
        self.direct_url_calls += 1
        return "https://storage.example/reusable-url"

    async def get_file_response(self, file_code):
        return {"downloaded": file_code.code}


class FakeRateLimit:
    def __init__(self):
        self.seen_ips = []

    def add_ip(self, ip):
        self.seen_ips.append(ip)


class ShareUsageSecurityTests(unittest.TestCase):
    def test_new_installations_default_to_secret_codes(self):
        self.assertEqual(DEFAULT_CONFIG["code_generate_type"], "secret")
        self.assertEqual(
            parse_setup_options({"expireStyle": ["day"]})["code_generate_type"],
            "secret",
        )
        self.assertIn('<option value="secret" selected>', build_setup_page())

    def test_atomic_usage_download_and_metadata_limits(self):
        asyncio.run(self._run_scenario())

    async def _run_scenario(self):
        original_config = dict(settings.user_config)
        original_metadata_limit = views.ip_limit["metadata"]
        settings.file_storage = "local"
        settings.jwt_secret = "test-download-secret"
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
            await self._assert_count_consumption_is_atomic()
            await self._assert_time_expiration_and_usage_are_atomic()
            await self._assert_download_url_is_single_use()
            await self._assert_text_share_downloads_as_txt()
            await self._assert_limited_files_do_not_expose_direct_urls()
            await self._assert_metadata_counts_all_attempts()
        finally:
            views.ip_limit["metadata"] = original_metadata_limit
            settings.user_config = original_config
            await Tortoise.close_connections()

    async def _assert_count_consumption_is_atomic(self):
        record = await FileCodes.create(
            code="atomic",
            prefix="atomic",
            suffix=".txt",
            expired_count=1,
            expired_at=await get_now() + datetime.timedelta(days=1),
        )
        stale_copies = await asyncio.gather(
            *(FileCodes.get(id=record.id) for _ in range(20))
        )

        consumed = await asyncio.gather(
            *(views.consume_file_usage(item) for item in stale_copies)
        )

        await record.refresh_from_db()
        self.assertEqual(sum(consumed), 1)
        self.assertEqual(record.expired_count, 0)
        self.assertEqual(record.used_count, 1)

    async def _assert_time_expiration_and_usage_are_atomic(self):
        valid = await FileCodes.create(
            code="time-valid",
            text="valid",
            expired_count=-1,
            expired_at=await get_now() + datetime.timedelta(minutes=5),
        )
        expired = await FileCodes.create(
            code="time-expired",
            text="expired",
            expired_count=-1,
            expired_at=await get_now() - datetime.timedelta(seconds=1),
        )
        valid_copies = await asyncio.gather(
            *(FileCodes.get(id=valid.id) for _ in range(20))
        )

        consumed = await asyncio.gather(
            *(views.consume_file_usage(item) for item in valid_copies)
        )

        self.assertTrue(all(consumed))
        self.assertFalse(await views.consume_file_usage(expired))
        await valid.refresh_from_db()
        await expired.refresh_from_db()
        self.assertEqual(valid.expired_count, -1)
        self.assertEqual(valid.used_count, 20)
        self.assertEqual(expired.used_count, 0)

    async def _assert_download_url_is_single_use(self):
        record = await FileCodes.create(
            code="single-use",
            prefix="report",
            suffix=".pdf",
            expired_count=1,
            expired_at=await get_now() + datetime.timedelta(days=1),
        )
        key = await get_select_token(record.code)

        with patch.dict(views.storages, {"local": FakeStorage}):
            selected = await views.select_file(
                data=views.SelectFileModel(code=record.code), ip="127.0.0.1"
            )
            await record.refresh_from_db()
            self.assertEqual(selected.detail["expired_count"], 1)
            self.assertEqual(record.expired_count, 1)
            self.assertEqual(record.used_count, 0)

            first = await views.download_file(key=key, code=record.code, ip="127.0.0.1")
            second = await views.download_file(key=key, code=record.code, ip="127.0.0.1")

        self.assertEqual(first, {"downloaded": record.code})
        self.assertEqual(second.code, 404)
        await record.refresh_from_db()
        self.assertEqual(record.expired_count, 0)
        self.assertEqual(record.used_count, 1)

    async def _assert_text_share_downloads_as_txt(self):
        record = await FileCodes.create(
            code="text-download",
            prefix="TAG",
            text="hello, 文本直链",
            expired_count=-1,
            expired_at=None,
        )

        with patch.dict(views.storages, {"local": FakeStorage}):
            response = await views.get_code_file(
                code=record.code, ip="127.0.0.1"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body.decode("utf-8"), record.text)
        self.assertEqual(response.media_type, "text/plain")
        self.assertEqual(
            response.headers["content-disposition"],
            "attachment; filename*=UTF-8''TAG.txt",
        )
        await record.refresh_from_db()
        self.assertEqual(record.used_count, 1)

    async def _assert_limited_files_do_not_expose_direct_urls(self):
        record = await FileCodes.create(
            code="proxy-only",
            prefix="archive",
            suffix=".zip",
            expired_count=2,
            expired_at=await get_now() + datetime.timedelta(days=1),
        )
        storage = FakeStorage()

        detail = await views.build_select_detail(record, storage)

        self.assertTrue(detail["download_url"].startswith("/share/download?"))
        self.assertEqual(storage.direct_url_calls, 0)

    async def _assert_metadata_counts_all_attempts(self):
        await FileCodes.create(
            code="metadata",
            text="hello",
            expired_count=-1,
            expired_at=None,
        )
        limiter = FakeRateLimit()
        views.ip_limit["metadata"] = limiter

        success = await views.get_file_metadata(code="metadata", ip="192.0.2.1")
        missing = await views.get_file_metadata(code="missing", ip="192.0.2.1")

        self.assertEqual(success.code, 200)
        self.assertEqual(missing.code, 404)
        self.assertEqual(limiter.seen_ips, ["192.0.2.1", "192.0.2.1"])


if __name__ == "__main__":
    unittest.main()
