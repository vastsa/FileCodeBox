import hashlib
import os
import tempfile
from core.logger import logger
from typing import BinaryIO, Optional

import aiofiles
import aiohttp
import asyncio
from pathlib import Path
import datetime
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


class OneDriveFileStorage(FileStorageInterface):
    def __init__(self):
        try:
            import msal
            from office365.graph_client import GraphClient
            from office365.runtime.client_request_exception import (
                ClientRequestException,
            )
        except ImportError:
            raise ImportError("请先安装`msal`和`Office365-REST-Python-Client`")
        self.msal = msal
        self.domain = settings.onedrive_domain
        self.client_id = settings.onedrive_client_id
        self.username = settings.onedrive_username
        self.password = settings.onedrive_password
        self.proxy = settings.onedrive_proxy
        self._ClientRequestException = ClientRequestException

        try:
            client = GraphClient(self.acquire_token_pwd)
            self.root_path = (
                client.me.drive.root.get_by_path(settings.onedrive_root_path)
                .get()
                .execute_query()
            )
        except ClientRequestException as e:
            if e.code == "itemNotFound":
                client.me.drive.root.create_folder(settings.onedrive_root_path)
                self.root_path = (
                    client.me.drive.root.get_by_path(
                        settings.onedrive_root_path)
                    .get()
                    .execute_query()
                )
            else:
                raise e
        except Exception as e:
            raise Exception("OneDrive验证失败，请检查配置是否正确\n" + str(e))

    def acquire_token_pwd(self):
        authority_url = f"https://login.microsoftonline.com/{self.domain}"
        app = self.msal.PublicClientApplication(
            authority=authority_url, client_id=self.client_id
        )
        result = app.acquire_token_by_username_password(
            username=self.username,
            password=self.password,
            scopes=["https://graph.microsoft.com/.default"],
        )
        return result

    def _get_path_str(self, path):
        if isinstance(path, str):
            path = path.replace("\\", "/").replace("//", "/").split("/")
        elif isinstance(path, Path):
            path = str(path).replace("\\", "/").replace("//", "/").split("/")
        else:
            raise TypeError("path must be str or Path")
        path[-1] = path[-1].split(".")[0]
        return "/".join(path)

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        """保存文件（自动创建目录；修复旧实现把 save_path 字符串当函数调用的崩溃）"""
        content = await asyncio.to_thread(stream.read)
        normalized = str(save_path).replace("\\", "/")
        name = await sanitize_filename(Path(normalized).name)
        dir_path = "/".join(normalized.split("/")[:-1])

        current_folder = self.root_path
        for part in dir_path.split("/"):
            if not part:
                continue
            try:
                current_folder = current_folder.get_by_path(part).get().execute_query()
            except self._ClientRequestException as e:
                if e.code == "itemNotFound":
                    current_folder = current_folder.create_folder(part).execute_query()
                else:
                    raise e

        await asyncio.to_thread(
            lambda: current_folder.get_by_path(name)
            .upload(name, content)
            .execute_query()
        )

    def _delete(self, save_path):
        path = self._get_path_str(save_path)
        try:
            self.root_path.get_by_path(path).delete_object().execute_query()
        except self._ClientRequestException as e:
            if e.code == "itemNotFound":
                pass
            else:
                raise e

    async def delete_file(self, file_code: StoredFile):
        await asyncio.to_thread(self._delete, file_code.get_file_path())

    def _convert_link_to_download_link(self, link):
        p1 = re.search(r"https://(.+)\.sharepoint\.com", link).group(1)
        p2 = re.search(r"personal/(.+)/", link).group(1)
        p3 = re.search(rf"{p2}/(.+)", link).group(1)
        return f"https://{p1}.sharepoint.com/personal/{p2}/_layouts/52/download.aspx?share={p3}"

    def _get_file_url(self, save_path, name):
        path = self._get_path_str(save_path)
        remote_file = self.root_path.get_by_path(path + "/" + name)
        expiration_datetime = datetime.datetime.now(
            tz=datetime.timezone.utc
        ) + datetime.timedelta(hours=1)
        expiration_datetime = expiration_datetime.strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        permission = remote_file.create_link(
            "view", "anonymous", expiration_datetime=expiration_datetime
        ).execute_query()
        return self._convert_link_to_download_link(permission.link.webUrl)

    async def get_file_response(self, file_code: StoredFile):
        try:
            filename = file_code.prefix + file_code.suffix
            try:
                link = await asyncio.to_thread(
                    self._get_file_url, file_code.get_file_path(), filename
                )
            except self._ClientRequestException as e:
                # 对象不存在时前置 404（与 local/S3/WebDAV 语义对齐），
                # 不再落入外层兜底的 503
                if str(getattr(e, "code", "")).lower() in {"itemnotfound", "404"}:
                    raise StorageError(
                        status_code=404, detail="文件已过期删除"
                    ) from e
                raise

            content_length = None  # 初始化为 None，表示未知大小

            # 创建ClientSession并复用
            session = aiohttp.ClientSession()
            
            # 尝试发送HEAD请求获取Content-Length
            try:
                async with session.head(link) as resp:
                    if resp.status == 200 and 'Content-Length' in resp.headers:
                        content_length = int(resp.headers['Content-Length'])
            except Exception:
                # 如果HEAD请求失败，则不提供 Content-Length
                pass
            
            async def stream_generator():
                try:
                    async with session.get(link) as resp:
                        if resp.status != 200:
                            raise StorageError(
                                status_code=resp.status,
                                detail=f"从OneDrive获取文件失败: {resp.status}"
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
        except StorageError:
            raise
        except Exception:
            raise StorageError(status_code=503, detail="服务代理下载异常，请稍后再试")

    async def get_file_url(self, file_code: StoredFile):
        if self.proxy:
            return await get_file_url(file_code.code)
        else:
            return await asyncio.to_thread(
                self._get_file_url,
                file_code.get_file_path(),
                f"{file_code.prefix}{file_code.suffix}",
            )

    def _save_chunk(self, chunk_path: str, chunk_data: bytes):
        """同步保存分片到 OneDrive"""
        path_parts = chunk_path.replace("\\", "/").split("/")
        filename = path_parts[-1]
        dir_path = "/".join(path_parts[:-1])
        
        # 确保目录存在
        current_folder = self.root_path
        for part in dir_path.split("/"):
            if part:
                try:
                    current_folder = current_folder.get_by_path(part).get().execute_query()
                except self._ClientRequestException as e:
                    if e.code == "itemNotFound":
                        current_folder = current_folder.create_folder(part).execute_query()
                    else:
                        raise e
        
        # 上传分片
        current_folder.upload(filename, chunk_data).execute_query()

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """保存分片到 OneDrive"""
        chunk_path = str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        await asyncio.to_thread(self._save_chunk, chunk_path, chunk_data)

    def _read_chunk(self, chunk_path: str) -> bytes:
        """同步读取分片"""
        path = self._get_path_str(chunk_path)
        file_obj = self.root_path.get_by_path(path).get().execute_query()
        return file_obj.get_content().execute_query().value

    def _upload_merged(self, save_path: str, data: bytes):
        """同步上传合并后的文件"""
        path_parts = save_path.replace("\\", "/").split("/")
        filename = path_parts[-1]
        dir_path = "/".join(path_parts[:-1])
        
        # 确保目录存在
        current_folder = self.root_path
        for part in dir_path.split("/"):
            if part:
                try:
                    current_folder = current_folder.get_by_path(part).get().execute_query()
                except self._ClientRequestException as e:
                    if e.code == "itemNotFound":
                        current_folder = current_folder.create_folder(part).execute_query()
                    else:
                        raise e
        
        current_folder.upload(filename, data).execute_query()

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """合并 OneDrive 上的分片文件，使用临时文件避免内存问题"""
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
                        chunk_data = await asyncio.to_thread(self._read_chunk, chunk_path)
                    except Exception as e:
                        raise ValueError(f"分片{i}文件不存在: {e}")

                    self._verify_and_hash_chunk(i, chunk_record, chunk_data, file_sha256)
                    await out_file.write(chunk_data)
                    del chunk_data  # 释放内存

            # 读取临时文件并上传
            async with aiofiles.open(temp_path, 'rb') as f:
                merged_content = await f.read()
            await asyncio.to_thread(self._upload_merged, save_path, merged_content)
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        return save_path, file_sha256.hexdigest()

    def _delete_chunk_dir(self, chunk_dir: str):
        """同步删除分片目录"""
        try:
            path = self._get_path_str(chunk_dir)
            self.root_path.get_by_path(path).delete_object().execute_query()
        except self._ClientRequestException as e:
            if e.code != "itemNotFound":
                raise e

    async def clean_chunks(self, upload_id: str, save_path: str):
        """清理 OneDrive 上的临时分片文件"""
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        try:
            await asyncio.to_thread(self._delete_chunk_dir, chunk_dir)
        except Exception as e:
            logger.warning(f"清理 OneDrive 分片时出错: {e}")

    def _file_exists(self, save_path: str) -> bool:
        """同步检查文件是否存在"""
        try:
            path = self._get_path_str(save_path)
            self.root_path.get_by_path(path).get().execute_query()
            return True
        except self._ClientRequestException as e:
            if e.code == "itemNotFound":
                return False
            raise e

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于OneDrive
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        return await asyncio.to_thread(self._file_exists, save_path)


