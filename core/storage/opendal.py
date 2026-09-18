import hashlib
import os
import tempfile
from core.logger import logger
from typing import BinaryIO, Optional

import aiofiles
import asyncio
from pathlib import Path
from core.errors import StorageError
from core.settings import settings
from core.utils import get_file_url

from core.storage._base import (
    FileStorageInterface,
    StoredDownload,
    StoredFile,
    build_attachment_headers,
)


class OpenDALFileStorage(FileStorageInterface):
    def __init__(self):
        try:
            import opendal
        except ImportError:
            raise ImportError('请先安装 `opendal`, 例如: "pip install opendal"')
        self.service = settings.opendal_scheme
        service_settings = {}
        for key, value in settings.items():
            if key.startswith("opendal_" + self.service):
                setting_name = key.split("_", 2)[2]
                service_settings[setting_name] = value
        self.operator = opendal.AsyncOperator(
            settings.opendal_scheme, **service_settings
        )

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        # 使用 asyncio.to_thread 避免阻塞事件循环
        content = await asyncio.to_thread(stream.read)
        await self.operator.write(save_path, content)

    async def delete_file(self, file_code: StoredFile):
        await self.operator.delete(file_code.get_file_path())

    async def get_file_url(self, file_code: StoredFile):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: StoredFile):
        try:
            filename = file_code.prefix + file_code.suffix
            content_length = None  # 初始化为 None，表示未知大小
            
            # 尝试获取文件大小
            try:
                stat_result = await self.operator.stat(file_code.get_file_path())
                if hasattr(stat_result, 'content_length') and stat_result.content_length:
                    content_length = stat_result.content_length
                elif hasattr(stat_result, 'size') and stat_result.size:
                    content_length = stat_result.size
            except Exception:
                # 如果获取大小失败，则不提供 Content-Length
                pass
            
            # 尝试使用流式读取器
            try:
                # OpenDAL 可能提供 reader 方法返回一个异步读取器
                reader = await self.operator.reader(file_code.get_file_path())
            except AttributeError:
                # 如果 reader 方法不存在，回退到全量读取（兼容旧版本）
                content = await self.operator.read(file_code.get_file_path())
                headers = build_attachment_headers(filename, content_length)
                return StoredDownload(
                    filename=filename,
                    headers=headers,
                    content=content,
                )
            
            async def stream_generator():
                chunk_size = 65536
                while True:
                    chunk = await reader.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            
            headers = build_attachment_headers(filename, content_length)
            return StoredDownload(
                filename=filename,
                headers=headers,
                stream_factory=stream_generator,
            )
        except Exception as e:
            logger.info(e)
            raise StorageError(status_code=404, detail="文件已过期删除")

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """保存分片到 OpenDAL 存储"""
        chunk_path = str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        await self.operator.write(chunk_path, chunk_data)

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """合并 OpenDAL 存储上的分片文件，使用临时文件避免内存问题"""
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)

        # 使用临时文件存储合并数据
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            async with aiofiles.open(temp_path, 'wb') as out_file:
                for i in range(total_chunks):
                    chunk_path = f"{chunk_dir}/{i}.part"
                    chunk_record = self._get_chunk_record(chunk_records, i)

                    try:
                        chunk_data = await self.operator.read(chunk_path)
                    except Exception as e:
                        raise ValueError(f"分片{i}文件不存在: {e}")

                    self._verify_and_hash_chunk(i, chunk_record, chunk_data, file_sha256)
                    await out_file.write(chunk_data)
                    del chunk_data  # 释放内存

            # 读取临时文件并写入存储
            async with aiofiles.open(temp_path, 'rb') as f:
                merged_content = await f.read()
            await self.operator.write(save_path, merged_content)
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """清理 OpenDAL 存储上的临时分片文件"""
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        try:
            # OpenDAL 支持递归删除
            await self.operator.remove_all(chunk_dir)
        except Exception as e:
            logger.warning(f"清理 OpenDAL 分片时出错: {e}")

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于OpenDAL存储
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        try:
            await self.operator.stat(save_path)
            return True
        except Exception:
            return False


