import hashlib
from core.logger import logger
import shutil
from typing import BinaryIO, Optional

import aiofiles
import asyncio
from pathlib import Path
from core.errors import StorageError
from core.settings import data_root
from core.utils import get_file_url, sanitize_filename

from core.storage._base import (
    FileStorageInterface,
    StoredDownload,
    StoredFile,
    build_attachment_headers,
)


class SystemFileStorage(FileStorageInterface):
    def __init__(self):
        self.chunk_size = 256 * 1024
        self.root_path = data_root

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """将相对路径解析到数据根目录内，阻止路径穿越。"""
        root = self.root_path.resolve()
        raw = str(relative_path or "").replace("\\", "/").lstrip("/")
        if any(part == ".." for part in raw.split("/")):
            raise ValueError("非法文件路径")
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("非法文件路径") from exc
        return candidate

    def _save(self, file, save_path):
        with open(save_path, "wb") as f:
            chunk = file.read(self.chunk_size)
            while chunk:
                f.write(chunk)
                chunk = file.read(self.chunk_size)

    def _prepare_save_path(self, directory: str, filename: str) -> Path:
        """Resolve + create the parent directory (blocking; run in a thread)."""
        safe_save_path = self._resolve_safe_path(
            f"{directory}/{filename}" if directory not in {"", "."} else filename
        )
        safe_save_path.parent.mkdir(parents=True, exist_ok=True)
        return safe_save_path

    def _prepare_chunk_path(
        self, save_path: str, upload_id: str, chunk_index: int
    ) -> Path:
        """Validate the target path and materialise the chunk directory."""
        self._resolve_safe_path(save_path)
        chunk_path = self._resolve_safe_path(
            str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        )
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        return chunk_path

    @staticmethod
    def _unlink_if_exists(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _delete_file_sync(self, relative_path: str) -> None:
        self._unlink_if_exists(self._resolve_safe_path(relative_path))

    def _stat_file_sync(self, relative_path: str) -> tuple[Path, int | None] | None:
        """Return (path, size); None when the file is gone.

        A stat that fails for another reason still yields the path with an
        unknown size, matching the old "omit Content-Length" behaviour.
        """
        file_path = self._resolve_safe_path(relative_path)
        try:
            return file_path, file_path.stat().st_size
        except FileNotFoundError:
            return None
        except OSError:
            return file_path, None

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        path_obj = Path(str(save_path).replace("\\", "/"))
        directory = str(path_obj.parent).replace("\\", "/").lstrip("/")
        # 提取原始文件名并进行清理
        filename = await sanitize_filename(path_obj.name)
        # 构建安全的完整保存路径（解析路径与建目录都是阻塞系统调用）
        safe_save_path = await asyncio.to_thread(
            self._prepare_save_path, directory, filename
        )
        await asyncio.to_thread(self._save, stream, safe_save_path)

    async def delete_file(self, file_code: StoredFile):
        await asyncio.to_thread(self._delete_file_sync, file_code.get_file_path())

    async def get_file_url(self, file_code: StoredFile):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: StoredFile):
        stat_result = await asyncio.to_thread(
            self._stat_file_sync, file_code.get_file_path()
        )
        if stat_result is None:
            raise StorageError(status_code=404, detail="文件已过期删除")
        file_path, size = stat_result
        filename = f"{file_code.prefix}{file_code.suffix}"
        headers = build_attachment_headers(filename, size)

        return StoredDownload(
            filename=filename,
            headers=headers,
            path=file_path,
        )

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """
        保存分片文件到本地文件系统
        :param upload_id: 上传会话ID
        :param chunk_index: 分片索引
        :param chunk_data: 分片数据
        :param chunk_hash: 分片哈希值
        :param save_path: 文件保存路径
        """
        chunk_path = await asyncio.to_thread(
            self._prepare_chunk_path, save_path, upload_id, chunk_index
        )
        # 使用临时文件写入，确保原子性
        temp_path = chunk_path.with_suffix('.tmp')
        try:
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(chunk_data)
            # 原子重命名
            await asyncio.to_thread(temp_path.rename, chunk_path)
        except Exception as e:
            await asyncio.to_thread(self._unlink_if_exists, temp_path)
            raise e

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """
        合并本地文件系统的分片文件并返回文件路径和完整哈希值

        按固定块（self.chunk_size）流式读写：内存峰值与分片大小无关，
        只与块大小有关（旧实现会把整片 read() 进内存）。
        :param upload_id: 上传会话ID
        :param chunk_info: 分片信息
        :param save_path: 文件保存路径
        :return: (文件路径, 文件哈希值)
        """
        output_path = await asyncio.to_thread(self._resolve_safe_path, save_path)
        await asyncio.to_thread(output_path.parent.mkdir, parents=True, exist_ok=True)
        chunk_base_dir = await asyncio.to_thread(
            self._resolve_safe_path,
            str(Path(save_path).parent / "chunks" / upload_id),
        )
        file_sha256 = hashlib.sha256()

        # 使用临时文件写入，确保原子性
        temp_output = output_path.with_suffix('.merging')
        try:
            async with aiofiles.open(temp_output, "wb") as out_file:
                for i in range(total_chunks):
                    # 获取分片记录
                    chunk_record = self._get_chunk_record(chunk_records, i)
                    chunk_path = chunk_base_dir / f"{i}.part"
                    chunk_sha256 = hashlib.sha256()
                    try:
                        async with aiofiles.open(chunk_path, "rb") as in_file:
                            while True:
                                block = await in_file.read(self.chunk_size)
                                if not block:
                                    break
                                chunk_sha256.update(block)
                                file_sha256.update(block)
                                await out_file.write(block)
                    except FileNotFoundError as exc:
                        raise ValueError(f"分片{i}文件不存在") from exc
                    self._verify_chunk_hash(i, chunk_record, chunk_sha256.hexdigest())
            # 原子重命名
            await asyncio.to_thread(temp_output.rename, output_path)
        except Exception as e:
            await asyncio.to_thread(self._unlink_if_exists, temp_output)
            raise e
        return str(output_path), file_sha256.hexdigest()

    def _clean_chunks_sync(self, upload_id: str, save_path: str) -> None:
        chunk_dir = self._resolve_safe_path(
            str(Path(save_path).parent / "chunks" / upload_id)
        )
        if chunk_dir.exists():
            try:
                shutil.rmtree(chunk_dir)
            except Exception as e:
                logger.warning(f"清理本地分片目录失败: {e}")
        # 清理父级 chunks 目录（如果为空）
        chunks_parent = chunk_dir.parent
        if chunks_parent.exists() and not any(chunks_parent.iterdir()):
            try:
                chunks_parent.rmdir()
            except Exception as e:
                logger.warning(f"清理 chunks 父目录失败: {e}")

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理本地文件系统的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        await asyncio.to_thread(self._clean_chunks_sync, upload_id, save_path)

    def _file_exists_sync(self, save_path: str) -> bool:
        try:
            file_path = self._resolve_safe_path(save_path)
        except ValueError:
            return False
        return file_path.exists()

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于本地文件系统
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        return await asyncio.to_thread(self._file_exists_sync, save_path)


