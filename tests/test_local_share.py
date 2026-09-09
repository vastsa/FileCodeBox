"""D2 回归：admin 本地文件分享此前必 500（read() 泄漏句柄 + save_file 误用
UploadFile 属性）。现在 save_file 接收 BinaryIO，read() 返回 bytes。"""
import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests.helpers import SettingsOverrideMixin, close_db, init_memory_db

from apps.admin.services import FileService, LocalFileClass


class LocalFileClassTests(unittest.TestCase):
    def test_read_returns_bytes_and_closes_handle(self):
        with TemporaryDirectory() as tmpdir:
            with patch("apps.admin.services.data_root", Path(tmpdir)), patch(
                "core.storage.data_root", Path(tmpdir)
            ):
                local = Path(tmpdir) / "local"
                local.mkdir()
                (local / "hello.txt").write_bytes(b"local-bytes")

                lf = LocalFileClass("hello.txt")
                self.assertEqual(lf.size, 11)
                data = asyncio.run(lf.read())
                self.assertEqual(data, b"local-bytes")


class ShareLocalFileTests(SettingsOverrideMixin, unittest.TestCase):
    def test_share_local_file_creates_code_and_saves_file(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                with patch("apps.admin.services.data_root", Path(tmpdir)), patch(
                    "core.storage.data_root", Path(tmpdir)
                ):
                    local = Path(tmpdir) / "local"
                    local.mkdir()
                    (local / "doc.txt").write_bytes(b"hello local share")

                    class Item:
                        filename = "doc.txt"
                        expire_value = 1
                        expire_style = "day"

                    service = FileService()
                    result = await service.share_local_file(Item())
                    self.assertIn("code", result)

                    saved = Path(tmpdir) / "share" / "data"
                    saved_files = [p for p in saved.rglob("*") if p.is_file()]
                    self.assertTrue(saved_files, "分享后文件应已落盘")
                    self.assertEqual(saved_files[0].read_bytes(), b"hello local share")
            finally:
                await close_db()


if __name__ == "__main__":
    unittest.main()
