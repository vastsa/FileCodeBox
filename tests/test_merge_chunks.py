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
from types import SimpleNamespace
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
                with patch("core.storage.local.data_root", Path(tmpdir)):
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


class MergeChunksStreamingTests(unittest.TestCase):
    """合并必须按块读取：峰值内存与分片大小无关，且哈希仍逐片校验。"""

    def test_reads_chunks_in_bounded_blocks(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        import core.storage.local as local_module

        with TemporaryDirectory() as tmpdir:
            with patch("core.storage.local.data_root", Path(tmpdir)):
                storage = SystemFileStorage()
                storage.chunk_size = 3
                save_path = "share/data/2026/01/01/uuid-stream/merged.bin"
                chunk_dir = (
                    Path(tmpdir) / "share/data/2026/01/01/uuid-stream/chunks/uid-stream"
                )
                chunk_dir.mkdir(parents=True)
                payloads = [b"abcdefghij", b"klm"]
                for index, data in enumerate(payloads):
                    (chunk_dir / f"{index}.part").write_bytes(data)

                records = {
                    index: SimpleNamespace(chunk_hash=_sha(data))
                    for index, data in enumerate(payloads)
                }

                read_sizes = []
                real_open = local_module.aiofiles.open

                class RecordingFile:
                    def __init__(self, inner):
                        self._inner = inner

                    async def read(self, *args):
                        read_sizes.append(args)
                        return await self._inner.read(*args)

                class RecordingContext:
                    def __init__(self, ctx):
                        self._ctx = ctx

                    async def __aenter__(self):
                        return RecordingFile(await self._ctx.__aenter__())

                    async def __aexit__(self, *exc_info):
                        return await self._ctx.__aexit__(*exc_info)

                def fake_open(path, mode="r", *args, **kwargs):
                    ctx = real_open(path, mode, *args, **kwargs)
                    if "b" in mode and "r" in mode:
                        return RecordingContext(ctx)
                    return ctx

                with patch.object(local_module.aiofiles, "open", fake_open):
                    out_path, digest = await storage.merge_chunks(
                        "uid-stream",
                        len(payloads),
                        storage.chunk_size,
                        save_path,
                        records,
                    )

                merged = b"".join(payloads)
                self.assertEqual(Path(out_path).read_bytes(), merged)
                self.assertEqual(digest, _sha(merged))
                # 每 3 字节一次读取：10 字节 -> 5 次（含 EOF），3 字节 -> 2 次
                self.assertEqual(read_sizes, [(3,)] * 7)


if __name__ == "__main__":
    unittest.main()
