# @Time    : 2023/8/11 20:06
# @Author  : Lan
# @File    : storage.py
# @Software: PyCharm
import base64
import hashlib
from core.logger import logger
import shutil
from typing import Optional
from urllib.parse import quote, unquote

import aiofiles
import aiohttp
import asyncio
from pathlib import Path
import datetime
import io
import re
import aioboto3
from botocore.config import Config
from fastapi import HTTPException, Response, UploadFile
from core.response import APIResponse
from core.settings import data_root, settings
from apps.base.models import FileCodes, UploadChunk
from core.utils import get_file_url, sanitize_filename
from fastapi.responses import FileResponse, StreamingResponse


class FileStorageInterface:

    async def save_file(self, file: UploadFile, save_path: str):
        """
        保存文件
        """
        raise NotImplementedError

    async def delete_file(self, file_code: FileCodes):
        """
        删除文件
        """
        raise NotImplementedError

    async def get_file_url(self, file_code: FileCodes):
        """
        获取文件分享的url

        如果服务不支持直接访问文件，可以通过服务器中转下载。
        此时，此方法可以调用 utils.py 中的 `get_file_url` 方法，获取服务器中转下载的url
        """
        raise NotImplementedError

    async def get_file_response(self, file_code: FileCodes):
        """
        获取文件响应

        如果服务不支持直接访问文件，则需要实现该方法，返回文件响应
        其余情况，可以不实现该方法
        """
        raise NotImplementedError

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """
        保存分片文件
        :param upload_id: 上传会话ID
        :param chunk_index: 分片索引
        :param chunk_data: 分片数据
        :param chunk_hash: 分片哈希值
        :param save_path: 文件保存路径
        """
        raise NotImplementedError

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """
        合并分片文件并返回文件路径和完整哈希值
        :param upload_id: 上传会话ID
        :param chunk_info: 分片信息
        :param save_path: 文件保存路径
        :return: (文件路径, 文件哈希值)
        """
        raise NotImplementedError

    async def generate_presigned_upload_url(self, save_path: str, expires_in: int = 900) -> Optional[str]:
        """
        生成预签名上传URL
        :param save_path: 文件保存路径
        :param expires_in: URL过期时间（秒），默认15分钟
        :return: 预签名URL，如果不支持直传则返回None
        """
        return None  # 默认不支持直传，使用代理模式

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        raise NotImplementedError

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        raise NotImplementedError


class SystemFileStorage(FileStorageInterface):
    def __init__(self):
        self.chunk_size = 256 * 1024
        self.root_path = data_root

    def _save(self, file, save_path):
        with open(save_path, "wb") as f:
            chunk = file.read(self.chunk_size)
            while chunk:
                f.write(chunk)
                chunk = file.read(self.chunk_size)

    async def save_file(self, file: UploadFile, save_path: str):
        path_obj = Path(save_path)
        directory = str(path_obj.parent)
        # 提取原始文件名并进行清理
        filename = await sanitize_filename(path_obj.name)
        # 构建安全的完整保存路径
        safe_save_path = self.root_path / directory / filename
        # 确保目录存在
        if not safe_save_path.parent.exists():
            safe_save_path.parent.mkdir(parents=True)
        await asyncio.to_thread(self._save, file.file, safe_save_path)

    async def delete_file(self, file_code: FileCodes):
        save_path = self.root_path / await file_code.get_file_path()
        if save_path.exists():
            save_path.unlink()

    async def get_file_url(self, file_code: FileCodes):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: FileCodes):
        file_path = self.root_path / await file_code.get_file_path()
        if not file_path.exists():
            return APIResponse(code=404, detail="文件已过期删除")
        filename = f"{file_code.prefix}{file_code.suffix}"
        encoded_filename = quote(filename, safe='')
        content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"
        
        # 优先使用文件系统大小
        content_length = file_code.size  # 默认使用数据库中的大小
        try:
            content_length = file_path.stat().st_size
        except Exception:
            # 如果获取文件大小失败，继续使用默认大小
            pass
        
        return FileResponse(
            file_path,
            media_type="application/octet-stream",
            headers={"Content-Disposition": content_disposition, "Content-Length": str(content_length)},
            filename=filename  # 保留原始文件名以备某些场景使用
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
        chunk_dir = self.root_path / save_path
        chunk_path = chunk_dir.parent / 'chunks' / upload_id / f"{chunk_index}.part"
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

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """
        合并本地文件系统的分片文件并返回文件路径和完整哈希值
        :param upload_id: 上传会话ID
        :param chunk_info: 分片信息
        :param save_path: 文件保存路径
        :return: (文件路径, 文件哈希值)
        """
        output_path = self.root_path / save_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_base_dir = output_path.parent / 'chunks' / upload_id
        file_sha256 = hashlib.sha256()
        
        # 使用临时文件写入，确保原子性
        temp_output = output_path.with_suffix('.merging')
        try:
            async with aiofiles.open(temp_output, "wb") as out_file:
                for i in range(chunk_info.total_chunks):
                    # 获取分片记录
                    chunk_record = await UploadChunk.filter(upload_id=upload_id, chunk_index=i).first()
                    if not chunk_record:
                        raise ValueError(f"分片{i}记录不存在")
                    chunk_path = chunk_base_dir / f"{i}.part"
                    if not chunk_path.exists():
                        raise ValueError(f"分片{i}文件不存在")
                    async with aiofiles.open(chunk_path, "rb") as in_file:
                        chunk_data = await in_file.read()
                        current_hash = hashlib.sha256(chunk_data).hexdigest()
                        if current_hash != chunk_record.chunk_hash:
                            raise ValueError(f"分片{i}哈希不匹配: 期望 {chunk_record.chunk_hash}, 实际 {current_hash}")
                        file_sha256.update(chunk_data)
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
        chunk_dir = (self.root_path / save_path).parent / 'chunks' / upload_id
        if chunk_dir.exists():
            try:
                shutil.rmtree(chunk_dir)
            except Exception as e:
                logger.info(f"清理本地分片目录失败: {e}")
        # 清理父级 chunks 目录（如果为空）
        chunks_parent = chunk_dir.parent
        if chunks_parent.exists() and not any(chunks_parent.iterdir()):
            try:
                chunks_parent.rmdir()
            except Exception as e:
                logger.info(f"清理 chunks 父目录失败: {e}")

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于本地文件系统
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        file_path = self.root_path / save_path
        return file_path.exists()


class S3FileStorage(FileStorageInterface):
    def __init__(self):
        self.access_key_id = settings.s3_access_key_id
        self.secret_access_key = settings.s3_secret_access_key
        self.bucket_name = settings.s3_bucket_name
        self.s3_hostname = settings.s3_hostname
        self.region_name = settings.s3_region_name
        self.signature_version = settings.s3_signature_version
        self.endpoint_url = settings.s3_endpoint_url or f"https://{self.s3_hostname}"
        self.aws_session_token = settings.aws_session_token
        self.proxy = settings.s3_proxy
        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
        )
        if not settings.s3_endpoint_url:
            self.endpoint_url = f"https://{self.s3_hostname}"
        else:
            # 如果提供了 s3_endpoint_url，则优先使用它
            self.endpoint_url = settings.s3_endpoint_url

    async def save_file(self, file: UploadFile, save_path: str):
        async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_session_token=self.aws_session_token,
                region_name=self.region_name,
                config=Config(signature_version=self.signature_version),
        ) as s3:
            await s3.put_object(
                Bucket=self.bucket_name,
                Key=save_path,
                Body=await file.read(),
                ContentType=file.content_type,
            )

    async def delete_file(self, file_code: FileCodes):
        async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region_name,
                config=Config(signature_version=self.signature_version),
        ) as s3:
            await s3.delete_object(
                Bucket=self.bucket_name, Key=await file_code.get_file_path()
            )

    async def get_file_response(self, file_code: FileCodes):
        try:
            filename = file_code.prefix + file_code.suffix
            content_length = file_code.size  # 默认使用数据库中的大小
            
            async with self.session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    region_name=self.region_name,
                    config=Config(signature_version=self.signature_version),
            ) as s3:
                # 首先尝试获取文件大小（HEAD请求）
                try:
                    head_response = await s3.head_object(
                        Bucket=self.bucket_name,
                        Key=await file_code.get_file_path()
                    )
                    # 从HEAD响应中获取Content-Length
                    if 'ContentLength' in head_response:
                        content_length = head_response['ContentLength']
                    elif 'Content-Length' in head_response['ResponseMetadata']['HTTPHeaders']:
                        content_length = int(head_response['ResponseMetadata']['HTTPHeaders']['Content-Length'])
                except Exception:
                    # 如果HEAD请求失败，继续使用默认大小
                    pass
                
                link = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": await file_code.get_file_path(),
                    },
                    ExpiresIn=3600,
                )
            
            async def stream_generator():
                async with aiohttp.ClientSession() as session:
                    async with session.get(link) as resp:
                        if resp.status != 200:
                            raise HTTPException(
                                status_code=resp.status,
                                detail=f"从S3获取文件失败: {resp.status}"
                            )
                        # 设置块大小（例如64KB）
                        chunk_size = 65536
                        while True:
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
            
            from fastapi.responses import StreamingResponse
            headers = {
                "Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode("latin-1")}"',
                "Content-Length": str(content_length)
            }
            return StreamingResponse(
                stream_generator(),
                media_type="application/octet-stream",
                headers=headers
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="服务代理下载异常，请稍后再试")

    async def get_file_url(self, file_code: FileCodes):
        if file_code.prefix == "文本分享":
            return file_code.text
        if self.proxy:
            return await get_file_url(file_code.code)
        else:
            async with self.session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    region_name=self.region_name,
                    config=Config(signature_version=self.signature_version),
            ) as s3:
                result = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": await file_code.get_file_path(),
                    },
                    ExpiresIn=3600,
                )
                return result

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """
        保存分片到 S3（使用独立对象存储每个分片）
        注意：这里不使用 S3 原生的 multipart upload，而是将每个分片作为独立对象存储
        """
        chunk_key = str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        async with self.session.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_session_token=self.aws_session_token,
            region_name=self.region_name,
            config=Config(signature_version=self.signature_version),
        ) as s3:
            # 将分片作为独立对象上传
            await s3.put_object(
                Bucket=self.bucket_name,
                Key=chunk_key,
                Body=chunk_data,
                Metadata={
                    'chunk-hash': chunk_hash,
                    'chunk-index': str(chunk_index)
                }
            )

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """
        合并 S3 上的分片文件
        由于分片是独立对象存储的，需要下载后合并再上传
        """
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        merged_data = io.BytesIO()
        
        async with self.session.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_session_token=self.aws_session_token,
            region_name=self.region_name,
            config=Config(signature_version=self.signature_version),
        ) as s3:
            # 按顺序读取并验证每个分片
            for i in range(chunk_info.total_chunks):
                chunk_key = f"{chunk_dir}/{i}.part"
                chunk_record = await UploadChunk.filter(upload_id=upload_id, chunk_index=i).first()
                if not chunk_record:
                    raise ValueError(f"分片{i}记录不存在")
                
                try:
                    response = await s3.get_object(
                        Bucket=self.bucket_name,
                        Key=chunk_key
                    )
                    chunk_data = await response['Body'].read()
                except Exception as e:
                    raise ValueError(f"分片{i}文件不存在: {e}")
                
                current_hash = hashlib.sha256(chunk_data).hexdigest()
                if current_hash != chunk_record.chunk_hash:
                    raise ValueError(f"分片{i}哈希不匹配: 期望 {chunk_record.chunk_hash}, 实际 {current_hash}")
                
                file_sha256.update(chunk_data)
                merged_data.write(chunk_data)
            
            # 上传合并后的文件
            merged_data.seek(0)
            await s3.put_object(
                Bucket=self.bucket_name,
                Key=save_path,
                Body=merged_data.getvalue(),
                ContentType='application/octet-stream'
            )
        
        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理 S3 上的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        async with self.session.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_session_token=self.aws_session_token,
            region_name=self.region_name,
            config=Config(signature_version=self.signature_version),
        ) as s3:
            try:
                # 列出并删除所有分片对象
                paginator = s3.get_paginator('list_objects_v2')
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=chunk_dir):
                    objects = page.get('Contents', [])
                    if objects:
                        delete_objects = [{'Key': obj['Key']} for obj in objects]
                        await s3.delete_objects(
                            Bucket=self.bucket_name,
                            Delete={'Objects': delete_objects}
                        )
            except Exception as e:
                logger.info(f"清理 S3 分片数据时出错: {e}")

    async def generate_presigned_upload_url(self, save_path: str, expires_in: int = 900) -> Optional[str]:
        """
        生成S3预签名上传URL
        :param save_path: 文件保存路径
        :param expires_in: URL过期时间（秒），默认15分钟
        :return: 预签名PUT URL
        """
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_session_token=self.aws_session_token,
            region_name=self.region_name,
            config=Config(signature_version=self.signature_version),
        ) as s3:
            return await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": save_path,
                },
                ExpiresIn=expires_in,
            )

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于S3
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_session_token=self.aws_session_token,
            region_name=self.region_name,
            config=Config(signature_version=self.signature_version),
        ) as s3:
            try:
                await s3.head_object(Bucket=self.bucket_name, Key=save_path)
                return True
            except Exception:
                return False


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

    def _save(self, file, save_path):
        content = file.file.read()
        name = save_path(file.filename)
        path = self._get_path_str(save_path)
        self.root_path.get_by_path(path).upload(name, content).execute_query()

    async def save_file(self, file: UploadFile, save_path: str):
        await asyncio.to_thread(self._save, file, save_path)

    def _delete(self, save_path):
        path = self._get_path_str(save_path)
        try:
            self.root_path.get_by_path(path).delete_object().execute_query()
        except self._ClientRequestException as e:
            if e.code == "itemNotFound":
                pass
            else:
                raise e

    async def delete_file(self, file_code: FileCodes):
        await asyncio.to_thread(self._delete, await file_code.get_file_path())

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

    async def get_file_response(self, file_code: FileCodes):
        try:
            filename = file_code.prefix + file_code.suffix
            link = await asyncio.to_thread(
                self._get_file_url, await file_code.get_file_path(), filename
            )
            
            content_length = file_code.size  # 默认使用数据库中的大小
            
            # 尝试发送HEAD请求获取Content-Length
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(link) as resp:
                        if resp.status == 200 and 'Content-Length' in resp.headers:
                            content_length = int(resp.headers['Content-Length'])
            except Exception:
                # 如果HEAD请求失败，继续使用默认大小
                pass
            
            async def stream_generator():
                async with aiohttp.ClientSession() as session:
                    async with session.get(link) as resp:
                        if resp.status != 200:
                            raise HTTPException(
                                status_code=resp.status,
                                detail=f"从OneDrive获取文件失败: {resp.status}"
                            )
                        chunk_size = 65536
                        while True:
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
            
            headers = {
                "Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode("latin-1")}"',
                "Content-Length": str(content_length)
            }
            return StreamingResponse(
                stream_generator(),
                media_type="application/octet-stream",
                headers=headers
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="服务代理下载异常，请稍后再试")

    async def get_file_url(self, file_code: FileCodes):
        if self.proxy:
            return await get_file_url(file_code.code)
        else:
            return await asyncio.to_thread(
                self._get_file_url,
                await file_code.get_file_path(),
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

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """合并 OneDrive 上的分片文件"""
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        merged_data = io.BytesIO()
        
        for i in range(chunk_info.total_chunks):
            chunk_path = f"{chunk_dir}/{i}.part"
            chunk_record = await UploadChunk.filter(upload_id=upload_id, chunk_index=i).first()
            if not chunk_record:
                raise ValueError(f"分片{i}记录不存在")
            
            try:
                chunk_data = await asyncio.to_thread(self._read_chunk, chunk_path)
            except Exception as e:
                raise ValueError(f"分片{i}文件不存在: {e}")
            
            current_hash = hashlib.sha256(chunk_data).hexdigest()
            if current_hash != chunk_record.chunk_hash:
                raise ValueError(f"分片{i}哈希不匹配: 期望 {chunk_record.chunk_hash}, 实际 {current_hash}")
            
            file_sha256.update(chunk_data)
            merged_data.write(chunk_data)
        
        # 上传合并后的文件
        merged_data.seek(0)
        await asyncio.to_thread(self._upload_merged, save_path, merged_data.getvalue())
        
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
            logger.info(f"清理 OneDrive 分片时出错: {e}")

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

    async def save_file(self, file: UploadFile, save_path: str):
        await self.operator.write(save_path, file.file.read())

    async def delete_file(self, file_code: FileCodes):
        await self.operator.delete(await file_code.get_file_path())

    async def get_file_url(self, file_code: FileCodes):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: FileCodes):
        try:
            filename = file_code.prefix + file_code.suffix
            content_length = file_code.size  # 默认使用数据库中的大小
            
            # 尝试获取文件大小
            try:
                stat_result = await self.operator.stat(await file_code.get_file_path())
                if hasattr(stat_result, 'content_length') and stat_result.content_length:
                    content_length = stat_result.content_length
                elif hasattr(stat_result, 'size') and stat_result.size:
                    content_length = stat_result.size
            except Exception:
                # 如果获取大小失败，继续使用默认大小
                pass
            
            # 尝试使用流式读取器
            try:
                # OpenDAL 可能提供 reader 方法返回一个异步读取器
                reader = await self.operator.reader(await file_code.get_file_path())
            except AttributeError:
                # 如果 reader 方法不存在，回退到全量读取（兼容旧版本）
                content = await self.operator.read(await file_code.get_file_path())
                headers = {
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(content_length)
                }
                return Response(
                    content, headers=headers, media_type="application/octet-stream"
                )
            
            async def stream_generator():
                chunk_size = 65536
                while True:
                    chunk = await reader.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            
            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(content_length)
            }
            return StreamingResponse(
                stream_generator(),
                media_type="application/octet-stream",
                headers=headers
            )
        except Exception as e:
            logger.info(e)
            raise HTTPException(status_code=404, detail="文件已过期删除")

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """保存分片到 OpenDAL 存储"""
        chunk_path = str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        await self.operator.write(chunk_path, chunk_data)

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """合并 OpenDAL 存储上的分片文件"""
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        merged_data = io.BytesIO()
        
        for i in range(chunk_info.total_chunks):
            chunk_path = f"{chunk_dir}/{i}.part"
            chunk_record = await UploadChunk.filter(upload_id=upload_id, chunk_index=i).first()
            if not chunk_record:
                raise ValueError(f"分片{i}记录不存在")
            
            try:
                chunk_data = await self.operator.read(chunk_path)
            except Exception as e:
                raise ValueError(f"分片{i}文件不存在: {e}")
            
            current_hash = hashlib.sha256(chunk_data).hexdigest()
            if current_hash != chunk_record.chunk_hash:
                raise ValueError(f"分片{i}哈希不匹配: 期望 {chunk_record.chunk_hash}, 实际 {current_hash}")
            
            file_sha256.update(chunk_data)
            merged_data.write(chunk_data)
        
        # 写入合并后的文件
        merged_data.seek(0)
        await self.operator.write(save_path, merged_data.getvalue())
        
        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """清理 OpenDAL 存储上的临时分片文件"""
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        try:
            # OpenDAL 支持递归删除
            await self.operator.remove_all(chunk_dir)
        except Exception as e:
            logger.info(f"清理 OpenDAL 分片时出错: {e}")

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


class WebDAVFileStorage(FileStorageInterface):
    _instance: Optional["WebDAVFileStorage"] = None

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.base_url = settings.webdav_url.rstrip("/") + "/"
            self.auth = aiohttp.BasicAuth(
                login=settings.webdav_username, password=settings.webdav_password
            )
            self._initialized = True

    def _build_url(self, path: str) -> str:
        encoded_path = quote(str(path.replace("\\", "/").lstrip("/")).lstrip("/"))
        return f"{self.base_url}{encoded_path}"

    async def _mkdir_p(self, directory_path: str):
        """递归创建目录（类似mkdir -p）"""
        path_obj = Path(unquote(directory_path))
        current_path = ""

        async with aiohttp.ClientSession(auth=self.auth) as session:
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
                                raise HTTPException(
                                    status_code=mkcol_resp.status,
                                    detail=f"目录创建失败: {content[:200]}",
                                )

    async def _is_dir_empty(self, dir_path: str) -> bool:
        """检查目录是否为空"""
        url = self._build_url(dir_path)

        async with aiohttp.ClientSession(auth=self.auth) as session:
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

    async def save_file(self, file: UploadFile, save_path: str):
        """保存文件（自动创建目录）"""
        path_obj = Path(save_path)
        directory_path = str(path_obj.parent)
        # 提取原始文件名并进行清理
        filename = await sanitize_filename(path_obj.name)
        # 构建安全的保存路径
        safe_save_path = str(Path(directory_path) / filename)

        try:
            # 先创建目录结构
            await self._mkdir_p(directory_path)
            # 上传文件
            url = self._build_url(safe_save_path)
            async with aiohttp.ClientSession(auth=self.auth) as session:
                content = await file.read()
                async with session.put(
                        url, data=content, headers={
                            "Content-Type": file.content_type}
                ) as resp:
                    if resp.status not in (200, 201, 204):
                        content = await resp.text()
                        raise HTTPException(
                            status_code=resp.status,
                            detail=f"文件上传失败: {content[:200]}",
                        )
        except aiohttp.ClientError as e:
            raise HTTPException(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def delete_file(self, file_code: FileCodes):
        """删除WebDAV文件及空目录"""
        file_path = await file_code.get_file_path()
        url = self._build_url(file_path)
        try:
            async with aiohttp.ClientSession(auth=self.auth) as session:
                # 删除文件
                async with session.delete(url) as resp:
                    if resp.status not in (200, 204, 404):
                        content = await resp.text()
                        raise HTTPException(
                            status_code=resp.status,
                            detail=f"WebDAV删除失败: {content[:200]}",
                        )

                # 使用同一个 session 删除空目录
                await self._delete_empty_dirs(file_path, session)

        except aiohttp.ClientError as e:
            raise HTTPException(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def get_file_url(self, file_code: FileCodes):
        return await get_file_url(file_code.code)

    async def get_file_response(self, file_code: FileCodes):
        """获取文件响应（代理模式）"""
        try:
            filename = file_code.prefix + file_code.suffix
            url = self._build_url(await file_code.get_file_path())
            content_length = file_code.size  # 默认使用数据库中的大小
            
            # 尝试发送HEAD请求获取Content-Length
            try:
                async with aiohttp.ClientSession(headers={
                    "Authorization": f"Basic {base64.b64encode(f'{settings.webdav_username}:{settings.webdav_password}'.encode()).decode()}"
                }) as session:
                    async with session.head(url) as resp:
                        if resp.status == 200 and 'Content-Length' in resp.headers:
                            content_length = int(resp.headers['Content-Length'])
            except Exception:
                # 如果HEAD请求失败，继续使用默认大小
                pass
            
            async def stream_generator():
                async with aiohttp.ClientSession(headers={
                    "Authorization": f"Basic {base64.b64encode(f'{settings.webdav_username}:{settings.webdav_password}'.encode()).decode()}"
                }) as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise HTTPException(
                                status_code=resp.status,
                                detail=f"文件获取失败{resp.status}: {await resp.text()}",
                            )
                        chunk_size = 65536
                        while True:
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
            
            headers = {
                "Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode()}"',
                "Content-Length": str(content_length)
            }
            return StreamingResponse(
                stream_generator(),
                media_type="application/octet-stream",
                headers=headers
            )
        except aiohttp.ClientError as e:
            raise HTTPException(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """保存分片到 WebDAV"""
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        chunk_path = f"{chunk_dir}/{chunk_index}.part"
        
        # 先创建目录结构
        await self._mkdir_p(chunk_dir)
        
        chunk_url = self._build_url(chunk_path)
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.put(chunk_url, data=chunk_data) as resp:
                if resp.status not in (200, 201, 204):
                    content = await resp.text()
                    raise HTTPException(
                        status_code=resp.status,
                        detail=f"分片上传失败: {content[:200]}"
                    )

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """
        合并 WebDAV 上的分片文件
        由于大多数 WebDAV 服务器不支持 PATCH 追加，这里下载所有分片后合并上传
        """
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        merged_data = io.BytesIO()
        
        async with aiohttp.ClientSession(auth=self.auth) as session:
            # 按顺序读取并验证每个分片
            for i in range(chunk_info.total_chunks):
                chunk_path = f"{chunk_dir}/{i}.part"
                chunk_url = self._build_url(chunk_path)
                
                # 获取分片记录
                chunk_record = await UploadChunk.filter(upload_id=upload_id, chunk_index=i).first()
                if not chunk_record:
                    raise ValueError(f"分片{i}记录不存在")
                
                # 下载分片数据
                async with session.get(chunk_url) as resp:
                    if resp.status != 200:
                        raise ValueError(f"分片{i}文件不存在或无法访问")
                    chunk_data = await resp.read()
                
                # 验证哈希
                current_hash = hashlib.sha256(chunk_data).hexdigest()
                if current_hash != chunk_record.chunk_hash:
                    raise ValueError(f"分片{i}哈希不匹配: 期望 {chunk_record.chunk_hash}, 实际 {current_hash}")
                
                file_sha256.update(chunk_data)
                merged_data.write(chunk_data)
            
            # 确保目标目录存在
            output_dir = str(Path(save_path).parent)
            await self._mkdir_p(output_dir)
            
            # 上传合并后的文件
            output_url = self._build_url(save_path)
            merged_data.seek(0)
            async with session.put(output_url, data=merged_data.getvalue()) as resp:
                if resp.status not in (200, 201, 204):
                    content = await resp.text()
                    raise HTTPException(
                        status_code=resp.status,
                        detail=f"合并文件上传失败: {content[:200]}"
                    )
        
        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理 WebDAV 上的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        chunk_dir_url = self._build_url(chunk_dir)
        async with aiohttp.ClientSession(auth=self.auth) as session:
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
                                        logger.info(f"删除分片文件失败: {file_path}")

                        # 删除分片目录
                        async with session.delete(chunk_dir_url) as delete_resp:
                            if delete_resp.status not in (200, 204, 404):
                                logger.info(f"删除分片目录失败: {chunk_dir_url}")
                    else:
                        logger.info(f"分片目录不存在: {chunk_dir_url}")
            except Exception as e:
                logger.info(f"清理 WebDAV 分片时出错: {e}")

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于WebDAV
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        url = self._build_url(save_path)
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.head(url) as resp:
                return resp.status == 200


storages = {
    "local": SystemFileStorage,
    "s3": S3FileStorage,
    "onedrive": OneDriveFileStorage,
    "opendal": OpenDALFileStorage,
    "webdav": WebDAVFileStorage,
}
