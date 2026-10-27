"""本地存储的阻塞文件操作必须下放线程池。

单核 VPS 上，事件循环里直接 unlink/rmtree/stat 会卡住所有并发请求；
这里用线程记录器钉住这些边界（测试进程里 asyncio.run 的主线程名为
MainThread，to_thread 运行在 asyncio_* 工作线程）。
"""
import shutil
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from core.errors import StorageError
from core.storage import StoredFile, SystemFileStorage


def _file_code(save_path: str) -> StoredFile:
    return StoredFile(
        file_path=save_path.rsplit("/", 1)[0],
        uuid_file_name=save_path.rsplit("/", 1)[1],
    )


async def test_delete_file_runs_in_worker_thread():
    with TemporaryDirectory() as tmpdir:
        with patch("core.storage.local.data_root", Path(tmpdir)):
            storage = SystemFileStorage()
            target = Path(tmpdir) / "share/data/2026/01/01/uuid/f.bin"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"payload")

            main_thread = threading.current_thread()
            recorded = {}
            real_unlink = Path.unlink

            def spy_unlink(self, *args, **kwargs):
                recorded["thread"] = threading.current_thread()
                return real_unlink(self, *args, **kwargs)

            with patch.object(Path, "unlink", spy_unlink):
                await storage.delete_file(
                    _file_code("share/data/2026/01/01/uuid/f.bin")
                )

            assert recorded["thread"] is not main_thread
            assert not target.exists()


async def test_clean_chunks_runs_in_worker_thread():
    with TemporaryDirectory() as tmpdir:
        with patch("core.storage.local.data_root", Path(tmpdir)):
            storage = SystemFileStorage()
            chunk_dir = Path(tmpdir) / "share/data/2026/01/01/uuid/chunks/upload-1"
            chunk_dir.mkdir(parents=True)
            (chunk_dir / "0.part").write_bytes(b"x")

            main_thread = threading.current_thread()
            recorded = {}
            real_rmtree = shutil.rmtree

            def spy_rmtree(path, *args, **kwargs):
                recorded["thread"] = threading.current_thread()
                return real_rmtree(path, *args, **kwargs)

            with patch("core.storage.local.shutil.rmtree", spy_rmtree):
                await storage.clean_chunks(
                    "upload-1", "share/data/2026/01/01/uuid/f.bin"
                )

            assert recorded["thread"] is not main_thread
            assert not chunk_dir.exists()


async def test_missing_download_stats_in_worker_thread():
    with TemporaryDirectory() as tmpdir:
        with patch("core.storage.local.data_root", Path(tmpdir)):
            storage = SystemFileStorage()
            (Path(tmpdir) / "share/data/2026/01/01/uuid").mkdir(parents=True)

            main_thread = threading.current_thread()
            recorded = {}
            real_stat = Path.stat

            def spy_stat(self, *args, **kwargs):
                recorded["thread"] = threading.current_thread()
                return real_stat(self, *args, **kwargs)

            with patch.object(Path, "stat", spy_stat):
                with pytest.raises(StorageError) as exc_info:
                    await storage.get_file_response(
                        _file_code("share/data/2026/01/01/uuid/ghost.bin")
                    )

            assert exc_info.value.status_code == 404
            assert recorded["thread"] is not main_thread


async def test_save_chunk_prepares_directory_in_worker_thread():
    with TemporaryDirectory() as tmpdir:
        with patch("core.storage.local.data_root", Path(tmpdir)):
            storage = SystemFileStorage()
            main_thread = threading.current_thread()
            recorded = {}
            real_prepare = SystemFileStorage._prepare_chunk_path

            def spy_prepare(self, save_path, upload_id, chunk_index):
                recorded["thread"] = threading.current_thread()
                return real_prepare(self, save_path, upload_id, chunk_index)

            with patch.object(SystemFileStorage, "_prepare_chunk_path", spy_prepare):
                await storage.save_chunk(
                    "upload-1",
                    0,
                    b"payload",
                    "unused",
                    "share/data/2026/01/01/uuid/f.bin",
                )

            assert recorded["thread"] is not main_thread
            chunk_path = (
                Path(tmpdir)
                / "share/data/2026/01/01/uuid/chunks/upload-1/0.part"
            )
            assert chunk_path.read_bytes() == b"payload"
