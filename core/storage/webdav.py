import base64
import hashlib
import os
import tempfile
from core.logger import logger
from typing import BinaryIO, Optional
from urllib.parse import quote, unquote

import aiofiles
import aiohttp
import asyncio
from pathlib import Path
import re
from core.errors import StorageError
from core.settings import settings
from core.utils import get_file_url, sanitize_filename
from starlette.background import BackgroundTask

from core.storage._base import (
    FileStorageInterface,
    StoredDownload,
    StoredFile,
    build_attachment_headers,
)


class WebDAVFileStorage(FileStorageInterface):
    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.base_url = settings.webdav_url.rstrip("/") + "/"
            # aiohttp 4.0 移除 BasicAuth(auth=...) 参数——改用编码后的 Authorization 头
            self.auth_headers = {
                "Authorization": aiohttp.encode_basic_auth(
                    settings.webdav_username, settings.webdav_password
                )
            }
            self._initialized = True

    def _build_url(self, path: str) -> str:
        encoded_path = quote(str(path.replace("\\", "/").lstrip("/")).lstrip("/"))
        return f"{self.base_url}{encoded_path}"

    async def _mkdir_p(self, directory_path: str):
        """递归创建目录（类似mkdir -p）"""
        path_obj = Path(unquote(directory_path))
        current_path = ""

        async with aiohttp.ClientSession(headers=self.auth_headers) as session:
            # 逐级检查目录是否存在
            for part in path_obj.parts:
                current_path = str(Path(current_path) / part)
                url = self._build_url(current_path)

                # 检查目录是否存在
                async with session.head(url) as resp:
                    if resp.status == 404:
                        # 创建目录
                        async with session.request("MKCOL", url) as mkcol_resp:
                            if mkcol_resp.status not in (200, 201, 409):
                                content = await mkcol_resp.text()
                                raise StorageError(
                                    status_code=mkcol_resp.status,
                                    detail=f"目录创建失败: {content[:200]}",
                                )

    async def _is_dir_empty(self, dir_path: str) -> bool:
        """检查目录是否为空"""
        url = self._build_url(dir_path)

        async with aiohttp.ClientSession(headers=self.auth_headers) as session:
            async with session.request("PROPFIND", url, headers={"Depth": "1"}) as resp:
                if resp.status != 207:  # 207 是 Multi-Status 响应
                    return False
                content = await resp.text()
                # 如果只有一个 response（当前目录），说明目录为空
                return content.count("<D:response>") <= 1

    async def _delete_empty_dirs(self, file_path: str, session: aiohttp.ClientSession):
        """递归删除空目录"""
        path_obj = Path(file_path)
        current_path = path_obj.parent

        while str(current_path) != ".":
            if not await self._is_dir_empty(str(current_path)):
                break

            url = self._build_url(str(current_path))
            async with session.delete(url) as resp:
                if resp.status not in (200, 204, 404):
                    break

            current_path = current_path.parent

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        """保存文件（自动创建目录，流式上传）"""
        path_obj = Path(save_path)
        directory_path = str(path_obj.parent)
        # 提取原始文件名并进行清理
        filename = await sanitize_filename(path_obj.name)
        # 构建安全的保存路径
        safe_save_path = str(Path(directory_path) / filename)

        try:
            # 先创建目录结构
            await self._mkdir_p(directory_path)
            # 上传文件（流式）
            url = self._build_url(safe_save_path)

            async def file_sender():
                """流式读取文件内容"""
                chunk_size = 256 * 1024  # 256KB chunks
                while True:
                    chunk = await asyncio.to_thread(stream.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk

            async with aiohttp.ClientSession(headers=self.auth_headers) as session:
                async with session.put(
                        url,
                        data=file_sender(),
                        headers={"Content-Type": content_type or "application/octet-stream"}
                ) as resp:
                    if resp.status not in (200, 201, 204):
                        content = await resp.text()
                        raise StorageError(
                            status_code=resp.status,
                            detail=f"文件上传失败: {content[:200]}",
                        )
        except aiohttp.ClientError as e:
            raise StorageError(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def delete_file(self, file_code: StoredFile):
        """删除WebDAV文件及空目录"""
        file_path = file_code.get_file_path()
        url = self._build_url(file_path)
        try:
            async with aiohttp.ClientSession(headers=self.auth_headers) as session:
                # 删除文件
                async with session.delete(url) as resp:
                    if resp.status not in (200, 204, 404):
                        content = await resp.text()
                        raise StorageError(
                            status_code=resp.status,
                            detail=f"WebDAV删除失败: {content[:200]}",
                        )

                # 使用同一个 session 删除空目录
                await self._delete_empty_dirs(file_path, session)

        except aiohttp.ClientError as e:
            raise StorageError(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def get_file_url(self, file_code: StoredFile):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: StoredFile):
        """获取文件响应（代理模式）"""
        try:
            filename = file_code.prefix + file_code.suffix
            url = self._build_url(file_code.get_file_path())
            content_length = None  # 初始化为 None，表示未知大小
            
            # 创建ClientSession并复用（包含认证头）
            session = aiohttp.ClientSession(headers={
                "Authorization": f"Basic {base64.b64encode(f'{settings.webdav_username}:{settings.webdav_password}'.encode()).decode()}"
            })
            
            # 尝试发送HEAD请求获取Content-Length；对象不存在时前置 404
            # （与 local/S3 语义对齐），连接层错误映射 503——两者都不能
            # 静默吞掉后签出 200 坏流。异常路径回收 session 防泄漏。
            try:
                try:
                    async with session.head(url) as resp:
                        if resp.status == 404:
                            raise StorageError(
                                status_code=404, detail="文件已过期删除"
                            )
                        if resp.status == 200 and 'Content-Length' in resp.headers:
                            content_length = int(resp.headers['Content-Length'])
                except StorageError:
                    raise
                except aiohttp.ClientError as e:
                    raise StorageError(
                        status_code=503, detail=f"WebDAV连接异常: {str(e)}"
                    ) from e
                except Exception:
                    # 其他 HEAD 异常不阻断：流式下载阶段会给出真实状态
                    pass

            except BaseException:
                await session.close()
                raise

            async def stream_generator():
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise StorageError(
                                status_code=resp.status,
                                detail=f"文件获取失败{resp.status}: {await resp.text()}",
                            )
                        chunk_size = 65536
                        while True:
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    await session.close()
            
            headers = build_attachment_headers(filename, content_length)
            return StoredDownload(
                filename=filename,
                headers=headers,
                stream_factory=stream_generator,
                # 兜底关闭会话：客户端中断时与 generator finally 双保险
                background=BackgroundTask(session.close),
            )
        except aiohttp.ClientError as e:
            raise StorageError(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """保存分片到 WebDAV"""
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        chunk_path = f"{chunk_dir}/{chunk_index}.part"
        
        # 先创建目录结构
        await self._mkdir_p(chunk_dir)
        
        chunk_url = self._build_url(chunk_path)
        async with aiohttp.ClientSession(headers=self.auth_headers) as session:
            async with session.put(chunk_url, data=chunk_data) as resp:
                if resp.status not in (200, 201, 204):
                    content = await resp.text()
                    raise StorageError(
                        status_code=resp.status,
                        detail=f"分片上传失败: {content[:200]}"
                    )

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """
        合并 WebDAV 上的分片文件
        使用临时文件避免内存问题
        """
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)

        # 使用临时文件存储合并数据，避免内存问题
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            async with aiohttp.ClientSession(headers=self.auth_headers) as session:
                # 按顺序读取并验证每个分片，写入临时文件
                async with aiofiles.open(temp_path, 'wb') as out_file:
                    for i in range(total_chunks):
                        chunk_path = f"{chunk_dir}/{i}.part"
                        chunk_url = self._build_url(chunk_path)

                        # 获取分片记录
                        chunk_record = self._get_chunk_record(chunk_records, i)

                        # 下载分片数据
                        async with session.get(chunk_url) as resp:
                            if resp.status != 200:
                                raise ValueError(f"分片{i}文件不存在或无法访问")
                            chunk_data = await resp.read()

                        # 验证哈希
                        self._verify_and_hash_chunk(i, chunk_record, chunk_data, file_sha256)
                        await out_file.write(chunk_data)
                        del chunk_data  # 释放内存

                # 确保目标目录存在
                output_dir = str(Path(save_path).parent)
                await self._mkdir_p(output_dir)

                # 流式上传合并后的文件
                output_url = self._build_url(save_path)

                async def file_sender():
                    async with aiofiles.open(temp_path, 'rb') as f:
                        while True:
                            chunk = await f.read(256 * 1024)
                            if not chunk:
                                break
                            yield chunk

                async with session.put(output_url, data=file_sender()) as resp:
                    if resp.status not in (200, 201, 204):
                        content = await resp.text()
                        raise StorageError(
                            status_code=resp.status,
                            detail=f"合并文件上传失败: {content[:200]}"
                        )
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理 WebDAV 上的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        chunk_dir_url = self._build_url(chunk_dir)
        async with aiohttp.ClientSession(headers=self.auth_headers) as session:
            try:
                # 检查分片目录是否存在
                async with session.request("PROPFIND", chunk_dir_url, headers={"Depth": "1"}) as resp:
                    if resp.status == 207:  # 207 表示 Multi-Status
                        # 获取目录下的所有分片文件
                        xml_data = await resp.text()
                        file_paths = re.findall(
                            r'<D:href>(.*?)</D:href>', xml_data)
                        for file_path in file_paths:
                            if file_path.endswith(".part"):
                                # 删除分片文件
                                file_url = self._build_url(file_path)
                                async with session.delete(file_url) as delete_resp:
                                    if delete_resp.status not in (200, 204, 404):
                                        logger.warning(f"删除分片文件失败: {file_path}")

                        # 删除分片目录
                        async with session.delete(chunk_dir_url) as delete_resp:
                            if delete_resp.status not in (200, 204, 404):
                                logger.warning(f"删除分片目录失败: {chunk_dir_url}")
                    else:
                        logger.info(f"分片目录不存在: {chunk_dir_url}")
            except Exception as e:
                logger.warning(f"清理 WebDAV 分片时出错: {e}")

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于WebDAV
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        url = self._build_url(save_path)
        async with aiohttp.ClientSession(headers=self.auth_headers) as session:
            async with session.head(url) as resp:
                return resp.status == 200


