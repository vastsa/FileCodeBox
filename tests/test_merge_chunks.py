"""Unit tests for SystemFileStorage.merge_chunks failure modes.

The happy path is already exercised end-to-end by the ASGI journey tests;
these target the guard rails: missing chunk records, missing chunk files,
hash mismatches, and that a failed merge leaves no half-written output.

Contract note: storage is ORM-free — the caller fetches chunk records and
passes them as a ``{chunk_index: record}`` dict keyed by index.
"""
import asyncio
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests.helpers import SettingsOverrideMixin, close_db, init_memory_db

from apps.base.models import UploadChunk
from core.storage import SystemFileStorage


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MergeChunksFailureTests(SettingsOverrideMixin, unittest.TestCase):
    def test_merge_failures_and_cleanup(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        with TemporaryDirectory() as tmpdir:
            await init_memory_db()
            try:
                with patch("core.storage.data_root", Path(tmpdir)):
                    storage = SystemFileStorage()
                    save_path = "share/data/2026/01/01/uuid-merge/merged.bin"
                    chunk_dir = Path(tmpdir) / "share/data/2026/01/01/uuid-merge/chunks/uid-merge"
                    chunk_dir.mkdir(parents=True)
                    chunk_a, chunk_b = b"AAAA", b"BBBB"
                    (chunk_dir / "0.part").write_bytes(chunk_a)
                    (chunk_dir / "1.part").write_bytes(chunk_b)

                    async def records():
                        rows = await UploadChunk.filter(upload_id="uid-merge").all()
                        return {r.chunk_index: r for r in rows}

                    await UploadChunk.create(
                        upload_id="uid-merge",
                        chunk_index=-1,
                        chunk_hash="0" * 64,
                        file_name="merged.bin",
                        file_size=8,
                        chunk_size=4,
                        total_chunks=2,
                        save_path=save_path,
                    )
                    await UploadChunk.create(
                        upload_id="uid-merge",
                        chunk_index=0,
                        chunk_hash=_sha(chunk_a),
                        file_name="merged.bin",
                        file_size=8,
                        chunk_size=4,
                        total_chunks=2,
                        save_path=save_path,
                        completed=True,
                    )

                    # 1) 分片 1 记录缺失
                    with self.assertRaisesRegex(ValueError, "分片1记录不存在"):
                        await storage.merge_chunks("uid-merge", 2, 4, save_path, await records())
                    self.assertFalse((Path(tmpdir) / save_path).exists(), "失败不得产出半成品文件")

                    # 2) 分片 1 记录存在但哈希与文件内容不匹配
                    await UploadChunk.create(
                        upload_id="uid-merge",
                        chunk_index=1,
                        chunk_hash=_sha(b"WRONG"),
                        file_name="merged.bin",
                        file_size=8,
                        chunk_size=4,
                        total_chunks=2,
                        save_path=save_path,
                        completed=True,
                    )
                    with self.assertRaisesRegex(ValueError, "哈希不匹配"):
                        await storage.merge_chunks("uid-merge", 2, 4, save_path, await records())
                    self.assertFalse((Path(tmpdir) / save_path).exists())

                    # 3) 记录匹配但磁盘文件缺失
                    (chunk_dir / "1.part").unlink()
                    with self.assertRaisesRegex(ValueError, "分片1文件不存在"):
                        await storage.merge_chunks("uid-merge", 2, 4, save_path, await records())

                    # 4) happy path：修正分片1记录哈希后合并成功，且输出哈希正确
                    (chunk_dir / "1.part").write_bytes(chunk_b)
                    wrong_record = await UploadChunk.filter(
                        upload_id="uid-merge", chunk_index=1
                    ).first()
                    wrong_record.chunk_hash = _sha(chunk_b)
                    await wrong_record.save()
                    out_path, file_hash = await storage.merge_chunks(
                        "uid-merge", 2, 4, save_path, await records()
                    )
                    self.assertTrue(Path(out_path).exists())
                    self.assertEqual(file_hash, _sha(chunk_a + chunk_b))
                    self.assertFalse((chunk_dir / "1.part").with_suffix(".merging").exists(), "临时合并文件应被重命名消费")

                    # 5) clean_chunks 清理分片目录
                    await storage.clean_chunks("uid-merge", save_path)
                    self.assertFalse(chunk_dir.exists())
            finally:
                await close_db()


if __name__ == "__main__":
    unittest.main()
