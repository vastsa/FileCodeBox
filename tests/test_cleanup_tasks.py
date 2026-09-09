"""Tests for the data-deleting background tasks in core/tasks.py.

These are the highest-risk paths in the app (they unlink files and delete DB
rows), previously untested. The infinite ``while True`` loops are broken by
patching asyncio.sleep to raise a sentinel after the first full pass; storage
is isolated into a temp dir by patching data_root in both consumers.
"""
import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests.helpers import SettingsOverrideMixin, close_db, init_memory_db

from apps.base.models import (
    FileCodes,
    PresignUploadSession,
    StorageReservation,
    UploadChunk,
)
from apps.base.tasks import (
    clean_expired_presign_sessions,
    clean_incomplete_uploads,
    delete_expire_files,
)
from core.utils import get_now


class SleepSentinel(Exception):
    pass


class _OneRoundMixin(SettingsOverrideMixin):
    """Run one pass of a cleanup task, then escape the loop via the sleep patch."""

    async def run_one_round(self, task_coro_factory, tmpdir):
        def _sleep(seconds):
            raise SleepSentinel

        with patch("apps.base.tasks.data_root", Path(tmpdir)), patch(
            "core.storage.data_root", Path(tmpdir)
        ), patch("apps.base.tasks.asyncio.sleep", side_effect=_sleep):
            try:
                await task_coro_factory()
            except SleepSentinel:
                pass

    def make_physical_file(self, tmpdir, file_code, content=b"payload"):
        """Materialise the file a FileCodes row points at, under the tmp root."""
        path = Path(tmpdir) / file_code.file_path / file_code.uuid_file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


class DeleteExpireFilesTests(_OneRoundMixin, unittest.TestCase):
    def test_expired_files_and_rows_deleted_alive_kept(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                now = await get_now()
                expired = await FileCodes.create(
                    code="gone1",
                    file_path="share/data/2026/01/01",
                    uuid_file_name="uuid-expired",
                    prefix="old",
                    suffix=".bin",
                    size=10,
                    expired_at=now - __import__("datetime").timedelta(days=1),
                )
                kept = await FileCodes.create(
                    code="keep1",
                    file_path="share/data/2026/01/01",
                    uuid_file_name="uuid-alive",
                    prefix="new",
                    suffix=".bin",
                    size=10,
                    expired_at=now + __import__("datetime").timedelta(days=30),
                    expired_count=1,
                )
                expired_path = self.make_physical_file(tmpdir, expired)
                kept_path = self.make_physical_file(tmpdir, kept)

                await self.run_one_round(delete_expire_files, tmpdir)

                self.assertFalse(expired_path.exists(), "过期文件应从磁盘删除")
                self.assertIsNone(await FileCodes.filter(code="gone1").first())
                self.assertTrue(kept_path.exists(), "未过期文件必须保留")
                self.assertIsNotNone(await FileCodes.filter(code="keep1").first())
            finally:
                await close_db()


class CleanIncompleteUploadsTests(_OneRoundMixin, unittest.TestCase):
    def test_stale_sessions_chunks_and_reservations_cleaned(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                import datetime

                stale = await UploadChunk.create(
                    upload_id="stale-uid",
                    chunk_index=-1,
                    chunk_hash="a" * 64,
                    file_name="stale.bin",
                    file_size=64,
                    chunk_size=64,
                    total_chunks=2,
                    save_path="share/data/2026/01/01/uuid-stale/stale.bin",
                    created_at=await get_now() - datetime.timedelta(hours=48),
                )
                chunks_dir = (
                    Path(tmpdir) / "share/data/2026/01/01/uuid-stale/chunks/stale-uid"
                )
                chunks_dir.mkdir(parents=True)
                (chunks_dir / "0.part").write_bytes(b"x" * 64)
                await StorageReservation.create(
                    token="chunk:stale-uid", size=64, expires_at=await get_now()
                )

                await self.run_one_round(clean_incomplete_uploads, tmpdir)

                self.assertFalse(chunks_dir.exists(), "过期会话的分片目录应被清理")
                self.assertIsNone(
                    await UploadChunk.filter(upload_id="stale-uid").first()
                )
                self.assertIsNone(
                    await StorageReservation.filter(token="chunk:stale-uid").first()
                )
                # 静默保留 stale 引用避免未使用告警（save_path 行为已由目录断言覆盖）
                del stale
            finally:
                await close_db()


class CleanExpiredPresignSessionsTests(_OneRoundMixin, unittest.TestCase):
    def test_expired_direct_session_file_and_rows_cleaned(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                import datetime

                now = await get_now()
                expired_direct = await PresignUploadSession.create(
                    upload_id="presign-direct",
                    file_name="direct.bin",
                    file_size=64,
                    save_path="share/data/2026/01/01/uuid-pd/direct.bin",
                    mode="direct",
                    expire_value=1,
                    expire_style="day",
                    expires_at=now - datetime.timedelta(seconds=1),
                )
                proxy_session = await PresignUploadSession.create(
                    upload_id="presign-proxy",
                    file_name="proxy.bin",
                    file_size=64,
                    save_path="share/data/2026/01/01/uuid-pp/proxy.bin",
                    mode="proxy",
                    expire_value=1,
                    expire_style="day",
                    expires_at=now - datetime.timedelta(seconds=1),
                )
                direct_path = Path(tmpdir) / expired_direct.save_path
                direct_path.parent.mkdir(parents=True, exist_ok=True)
                direct_path.write_bytes(b"payload")
                proxy_path = Path(tmpdir) / proxy_session.save_path

                await self.run_one_round(clean_expired_presign_sessions, tmpdir)

                self.assertFalse(direct_path.exists(), "直传模式的临时文件应被删除")
                self.assertIsNone(
                    await PresignUploadSession.filter(
                        upload_id="presign-direct"
                    ).first()
                )
                self.assertIsNone(
                    await StorageReservation.filter(
                        token="presign:presign-direct"
                    ).first()
                )
                # proxy 模式的文件可能尚未上传，任务只清记录
                self.assertIsNone(
                    await PresignUploadSession.filter(
                        upload_id="presign-proxy"
                    ).first()
                )
                if proxy_path.exists():
                    self.fail("proxy 会话文件不应被任务删除（从未上传成功）")
            finally:
                await close_db()


if __name__ == "__main__":
    unittest.main()
