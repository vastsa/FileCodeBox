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

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        path_obj = Path(str(save_path).replace("\\", "/"))
        directory = str(path_obj.parent).replace("\\", "/").lstrip("/")
        # 提取原始文件名并进行清理
        filename = await sanitize_filename(path_obj.name)
        # 构建安全的完整保存路径
        safe_save_path = self._resolve_safe_path(f"{directory}/{filename}" if directory not in {"", "."} else filename)
        # 确保目录存在
        if not safe_save_path.parent.exists():
            safe_save_path.parent.mkdir(parents=True)
        await asyncio.to_thread(self._save, stream, safe_save_path)

    async def delete_file(self, file_code: StoredFile):
        save_path = self._resolve_safe_path(file_code.get_file_path())
        if save_path.exists():
            save_path.unlink()

    async def get_file_url(self, file_code: StoredFile):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: StoredFile):
        file_path = self._resolve_safe_path(file_code.get_file_path())
        if not file_path.exists():
            raise StorageError(status_code=404, detail="文件已过期删除")
        filename = f"{file_code.prefix}{file_code.suffix}"
        try:
            headers = build_attachment_headers(filename, file_path.stat().st_size)
        except OSError:
            # 文件大小不可得时省略 Content-Length
            headers = build_attachment_headers(filename)
        
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
        # 先校验目标文件路径合法，再将分片落到同级 chunks 目录。
        self._resolve_safe_path(save_path)
        chunk_path = self._resolve_safe_path(
            str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        )
        if not chunk_path.parent.exists():
            chunk_path.parent.mkdir(parents=True, exist_ok=True)
        # 使用临时文件写入，确保原子性
        temp_path = chunk_path.with_suffix('.tmp')
        try:
            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(chunk_data)
            # 原子重命名
            temp_path.rename(chunk_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise e

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """
        合并本地文件系统的分片文件并返回文件路径和完整哈希值
        :param upload_id: 上传会话ID
        :param chunk_info: 分片信息
        :param save_path: 文件保存路径
        :return: (文件路径, 文件哈希值)
        """
        output_path = self._resolve_safe_path(save_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_base_dir = self._resolve_safe_path(
            str(Path(save_path).parent / "chunks" / upload_id)
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
                    if not chunk_path.exists():
                        raise ValueError(f"分片{i}文件不存在")
                    async with aiofiles.open(chunk_path, "rb") as in_file:
                        chunk_data = await in_file.read()
                        self._verify_and_hash_chunk(i, chunk_record, chunk_data, file_sha256)
                        await out_file.write(chunk_data)
            # 原子重命名
            temp_output.rename(output_path)
        except Exception as e:
            if temp_output.exists():
                temp_output.unlink()
            raise e
        return str(output_path), file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理本地文件系统的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
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

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于本地文件系统
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        try:
            file_path = self._resolve_safe_path(save_path)
        except ValueError:
            return False
        return file_path.exists()


