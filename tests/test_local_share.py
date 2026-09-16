"""Local NAS share: nested browse + zero-copy extract codes (issue #532)."""
import asyncio
import datetime
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException

from apps.admin.services import FileService, LocalFileClass, LocalFileService
from apps.base.local_share import LOCAL_REF_MARKER, is_local_ref
from apps.base.models import FileCodes
from apps.base.quota import get_storage_usage, reserve_storage
from apps.base.tasks import delete_expire_files
from tests.helpers import SettingsOverrideMixin, close_db, init_memory_db
from core.settings import settings
from core.utils import get_now


class SleepSentinel(Exception):
    pass


class LocalFileClassTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "local").mkdir()
        (self.root / "local" / "safe.txt").write_bytes(b"ok")
        (self.root / "local" / "movies").mkdir()
        (self.root / "local" / "movies" / "a.bin").write_bytes(b"nested")
        self._patch = patch("core.settings.data_root", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()

    def test_rejects_dotdot_filename(self):
        with self.assertRaises(HTTPException) as ctx:
            LocalFileClass("../etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_nested_dotdot(self):
        with self.assertRaises(HTTPException) as ctx:
            LocalFileClass("movies/../../etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_absolute_filename(self):
        with self.assertRaises(HTTPException) as ctx:
            LocalFileClass("/etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_allows_basename_inside_local(self):
        local_file = LocalFileClass("safe.txt")
        self.assertTrue(asyncio.run(local_file.exists()))
        self.assertEqual(local_file.file, "safe.txt")
        self.assertEqual(local_file.path, (self.root / "local" / "safe.txt").resolve())

    def test_allows_nested_relative(self):
        local_file = LocalFileClass("movies/a.bin")
        self.assertTrue(asyncio.run(local_file.exists()))
        self.assertEqual(local_file.file, "movies/a.bin")
        self.assertEqual(local_file.name, "a.bin")
        self.assertEqual(local_file.size, 6)


class LocalFileServiceListTests(unittest.TestCase):
    def test_lists_nested_dirs_and_files(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            movies = root / "local" / "movies"
            movies.mkdir(parents=True)
            (root / "local" / "readme.txt").write_bytes(b"hi")
            (movies / "a.bin").write_bytes(b"nested")
            with patch("core.settings.data_root", root):
                service = LocalFileService()
                root_listing = await service.list_files("")
                self.assertEqual(root_listing["path"], "")
                names = {item["name"]: item for item in root_listing["items"]}
                self.assertEqual(names["movies"]["type"], "dir")
                self.assertEqual(names["readme.txt"]["type"], "file")

                nested = await service.list_files("movies")
                self.assertEqual(nested["path"], "movies")
                self.assertEqual(nested["parent"], "")
                self.assertEqual(nested["items"][0]["path"], "movies/a.bin")
                self.assertEqual(nested["items"][0]["file"], "a.bin")


class ShareLocalFileTests(SettingsOverrideMixin, unittest.TestCase):
    def test_share_local_file_is_zero_copy(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                root = Path(tmpdir)
                movies = root / "local" / "movies"
                movies.mkdir(parents=True)
                source = movies / "doc.txt"
                source.write_bytes(b"hello local share")
                with patch("core.settings.data_root", root), patch(
                    "core.storage.data_root", root
                ):
                    class Item:
                        filename = "movies/doc.txt"
                        expire_value = 1
                        expire_style = "day"

                    result = await FileService().share_local_file(Item())
                    self.assertIn("code", result)
                    self.assertEqual(result["name"], "doc.txt")
                    self.assertEqual(result["path"], "movies/doc.txt")

                    record = await FileCodes.get(code=result["code"])
                    self.assertTrue(is_local_ref(record))
                    self.assertEqual(record.file_path, LOCAL_REF_MARKER)
                    self.assertEqual(record.uuid_file_name, "movies/doc.txt")
                    self.assertTrue(source.exists())
                    share_files = [
                        p for p in (root / "share").rglob("*") if p.is_file()
                    ] if (root / "share").exists() else []
                    self.assertFalse(share_files)
            finally:
                await close_db()


class LocalRefCleanupTests(SettingsOverrideMixin, unittest.TestCase):
    def test_expire_deletes_record_but_keeps_original(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                root = Path(tmpdir)
                source = root / "local" / "keep.bin"
                source.parent.mkdir(parents=True)
                source.write_bytes(b"keep-me")
                now = await get_now()
                await FileCodes.create(
                    code="nas1",
                    prefix="keep",
                    suffix=".bin",
                    uuid_file_name="keep.bin",
                    file_path=LOCAL_REF_MARKER,
                    size=7,
                    expired_at=now - datetime.timedelta(days=1),
                    expired_count=-1,
                )

                def _sleep(_seconds):
                    raise SleepSentinel

                with patch("core.settings.data_root", root), patch(
                    "core.storage.data_root", root
                ), patch("apps.base.tasks.data_root", root), patch(
                    "apps.base.tasks.asyncio.sleep", side_effect=_sleep
                ):
                    try:
                        await delete_expire_files()
                    except SleepSentinel:
                        pass

                self.assertTrue(source.exists())
                self.assertFalse(await FileCodes.filter(code="nas1").exists())
            finally:
                await close_db()


class LocalShareHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_browse_share_and_download(self):
        import httpx
        from tests.conftest import TEST_ADMIN_PASSWORD
        from tests.test_api_contract import _login

        import main

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            local_dir = root / "local" / "movies"
            local_dir.mkdir(parents=True)
            source = local_dir / "clip.bin"
            source.write_bytes(b"nas-bytes")
            await init_memory_db()
            try:
                from apps.base.utils import ip_limit

                for limiter in ip_limit.values():
                    limiter.ips.clear()
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test", follow_redirects=True
                ) as client:
                    setup = await client.post(
                        "/setup",
                        json={
                            "admin_password": TEST_ADMIN_PASSWORD,
                            "confirm_password": TEST_ADMIN_PASSWORD,
                            "site_name": "local-share-tests",
                            "expire_style": ["day", "forever", "count"],
                        },
                        headers={"Accept": "application/json"},
                    )
                    self.assertEqual(setup.status_code, 200, setup.text)
                    token = await _login(client)
                    headers = {"Authorization": f"Bearer {token}"}

                    with patch("core.settings.data_root", root):
                        listing = await client.get(
                            "/admin/local/lists", params={"path": "movies"}, headers=headers
                        )
                        self.assertEqual(listing.status_code, 200, listing.text)
                        payload = listing.json()["detail"]
                        self.assertEqual(payload["path"], "movies")
                        self.assertEqual(payload["items"][0]["path"], "movies/clip.bin")

                        share = await client.post(
                            "/admin/local/share",
                            json={
                                "filename": "movies/clip.bin",
                                "expire_style": "day",
                                "expire_value": 1,
                            },
                            headers=headers,
                        )
                        self.assertEqual(share.status_code, 200, share.text)
                        code = share.json()["detail"]["code"]

                        download = await client.get("/share/select/", params={"code": code})
                        self.assertEqual(download.status_code, 200, download.text)
                        self.assertEqual(download.content, b"nas-bytes")
                        self.assertTrue(source.exists())
            finally:
                await close_db()


class LocalRefQuotaTests(SettingsOverrideMixin, unittest.TestCase):
    def test_local_ref_does_not_consume_quota(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        settings.storage_limit = 100
        await init_memory_db()
        try:
            await FileCodes.create(
                code="nas-big",
                size=10_000,
                expired_count=-1,
                file_path=LOCAL_REF_MARKER,
                uuid_file_name="movies/huge.bin",
            )
            await FileCodes.create(code="owned", size=20, expired_count=-1)
            usage = await get_storage_usage()
            self.assertEqual(usage["used"], 20)
            await reserve_storage("upload-ok", 50, 300)
            usage = await get_storage_usage()
            self.assertEqual(usage["reserved"], 50)
            self.assertEqual(usage["available"], 30)
        finally:
            await close_db()


if __name__ == "__main__":
    unittest.main()
