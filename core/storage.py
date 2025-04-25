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
from core.utils import get_file_url
from fastapi.responses import FileResponse


class FileStorageInterface:
    _instance: Optional["FileStorageInterface"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FileStorageInterface, cls).__new__(
                cls, *args, **kwargs
            )
        return cls._instance

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
        save_path = self.root_path / save_path
        if not save_path.parent.exists():
            save_path.parent.mkdir(parents=True)
        await asyncio.to_thread(self._save, file.file, save_path)

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
        return FileResponse(
            file_path,
            headers={"Content-Disposition": content_disposition},
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
        chunk_path = chunk_dir.parent / 'chunks' / f"{chunk_index}.part"
        if not chunk_path.parent.exists():
            chunk_path.parent.mkdir(parents=True)
        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(chunk_data)

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        """
        合并本地文件系统的分片文件并返回文件路径和完整哈希值
        :param upload_id: 上传会话ID
        :param chunk_info: 分片信息
        :param save_path: 文件保存路径
        :return: (文件路径, 文件哈希值)
        """
        output_dir = self.root_path / save_path
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        file_sha256 = hashlib.sha256()
        async with aiofiles.open(output_dir, "wb") as out_file:
            for i in range(chunk_info.total_chunks):
                # 获取分片记录
                chunk_record = await UploadChunk.get(upload_id=upload_id, chunk_index=i)
                chunk_path = output_dir.parent / 'chunks' / f"{i}.part"
                async with aiofiles.open(chunk_path, "rb") as in_file:
                    chunk_data = await in_file.read()
                    current_hash = hashlib.sha256(chunk_data).hexdigest()
                    if current_hash != chunk_record.chunk_hash:
                        raise ValueError(f"分片{i}哈希不匹配")
                    file_sha256.update(chunk_data)
                    await out_file.write(chunk_data)
        return output_dir, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理本地文件系统的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        chunk_dir = (self.root_path / save_path).parent / 'chunks'
        if chunk_dir.exists():
            shutil.rmtree(chunk_dir)


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
            async with self.session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    region_name=self.region_name,
                    config=Config(signature_version=self.signature_version),
            ) as s3:
                link = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": await file_code.get_file_path(),
                    },
                    ExpiresIn=3600,
                )
            tmp = io.BytesIO()
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    tmp.write(await resp.read())
            tmp.seek(0)
            content = tmp.read()
            tmp.close()
            return Response(
                content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode("latin-1")}"'
                },
            )
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
        chunk_key = str(Path(save_path).parent / "chunks" /
                        upload_id / f"{chunk_index}.part")
        async with self.session.client('s3') as s3:
            response = await s3.upload_part(
                Bucket=self.bucket_name,
                Key=chunk_key,
                PartNumber=chunk_index + 1,
                UploadId=upload_id,
                Body=chunk_data
            )
            await s3.put_object_tagging(
                Bucket=self.bucket_name,
                Key=chunk_key,
                Tagging={
                    'TagSet': [
                        {'Key': 'ChunkHash', 'Value': chunk_hash},
                        {'Key': 'ETag', 'Value': response['ETag']}
                    ]
                }
            )

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        async with self.session.client('s3') as s3:
            # 获取所有分片
            parts = await s3.list_parts(
                Bucket=self.bucket_name,
                Key=chunk_dir,
                UploadId=upload_id
            )
            part_list = []
            for part in parts['Parts']:
                part_number = part['PartNumber']
                chunk_index = part_number - 1
                chunk_record = await UploadChunk.get(upload_id=upload_id, chunk_index=chunk_index)
                response = await s3.get_object(
                    Bucket=self.bucket_name,
                    Key=f"{chunk_dir}/{chunk_index}.part",
                    PartNumber=part_number
                )
                chunk_data = await response['Body'].read()
                current_hash = hashlib.sha256(chunk_data).hexdigest()
                if current_hash != chunk_record.chunk_hash:
                    raise Exception(f"分片{chunk_index}哈希不匹配")
                file_sha256.update(chunk_data)
                part_list.append(
                    {'PartNumber': part_number, 'ETag': part['ETag']})
            # 完成合并
            await s3.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=save_path,
                UploadId=upload_id,
                MultipartUpload={'Parts': part_list}
            )
        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理 S3 上的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        async with self.session.client('s3') as s3:
            try:
                # 终止未完成的分片上传会话
                await s3.abort_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=chunk_dir,
                    UploadId=upload_id
                )
            except Exception as e:
                # 如果上传会话不存在或其他错误，忽略
                logger.info(f"清理 S3 分片时出错: {e}")

            try:
                # 清理已上传的分片数据
                parts = await s3.list_parts(
                    Bucket=self.bucket_name,
                    Key=chunk_dir,
                    UploadId=upload_id
                )
                for part in parts.get('Parts', []):
                    await s3.delete_object(
                        Bucket=self.bucket_name,
                        Key=f"{chunk_dir}/{part['PartNumber'] - 1}.part"
                    )
            except Exception as e:
                # 如果分片数据不存在或其他错误，忽略
                logger.info(f"清理 S3 分片数据时出错: {e}")


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
        name = file.filename
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
            tmp = io.BytesIO()
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    tmp.write(await resp.read())
            tmp.seek(0)
            content = tmp.read()
            tmp.close()
            return Response(
                content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode("latin-1")}"'
                },
            )
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
            content = await self.operator.read(await file_code.get_file_path())
            headers = {
                "Content-Disposition": f'attachment; filename="{filename}"'}
            return Response(
                content, headers=headers, media_type="application/octet-stream"
            )
        except Exception as e:
            logger.info(e)
            raise HTTPException(status_code=404, detail="文件已过期删除")


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
        # 分离文件名和目录路径
        path_obj = Path(save_path)
        directory_path = str(path_obj.parent)
        try:
            # 先创建目录结构
            await self._mkdir_p(directory_path)
            # 上传文件
            url = self._build_url(save_path)
            async with aiohttp.ClientSession(auth=self.auth) as session:
                content = await file.read()  # 注意：大文件需要分块读取
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
            async with aiohttp.ClientSession(headers={
                "Authorization": f"Basic {base64.b64encode(f'{settings.webdav_username}:{settings.webdav_password}'.encode()).decode()}"
            }) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise HTTPException(
                            status_code=resp.status,
                            detail=f"文件获取失败{resp.status}: {await resp.text()}",
                        )
                    # 读取内容到内存
                    content = await resp.read()
                    return Response(
                        content=content,
                        media_type=resp.headers.get(
                            "Content-Type", "application/octet-stream"
                        ),
                        headers={
                            "Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode()}"'
                        },
                    )
        except aiohttp.ClientError as e:
            raise HTTPException(
                status_code=503, detail=f"WebDAV连接异常: {str(e)}")

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        chunk_path = str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        chunk_url = self._build_url(chunk_path)
        async with aiohttp.ClientSession(auth=self.auth) as session:
            await session.put(chunk_url, data=chunk_data)
            propfind_url = self._build_url(chunk_path)
            headers = {
                'Content-Type': 'application/xml; charset=utf-8', 'Depth': '0'}
            body = f"""
                <D:propertyupdate xmlns:D="DAV:">
                    <D:set>
                        <D:prop>
                            <ChunkHash xmlns="urn:filecodebox">{chunk_hash}</ChunkHash>
                        </D:prop>
                    </D:set>
                </D:propertyupdate>
            """
            await session.request('PROPPATCH', propfind_url, headers=headers, data=body)

    async def merge_chunks(self, upload_id: str, chunk_info: UploadChunk, save_path: str) -> tuple[str, str]:
        file_sha256 = hashlib.sha256()
        output_url = self._build_url(save_path)
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        async with aiohttp.ClientSession(auth=self.auth) as session:
            await session.put(output_url, headers={'Content-Length': '0'})
            for i in range(chunk_info.total_chunks):
                chunk_path = f"{chunk_dir}/{i}.part"
                chunk_url = self._build_url(chunk_path)
                propfind_url = self._build_url(chunk_path)
                headers = {
                    'Content-Type': 'application/xml; charset=utf-8', 'Depth': '0'}
                body = """
                    <D:propfind xmlns:D="DAV:">
                        <D:prop>
                            <ChunkHash xmlns="urn:filecodebox"/>
                        </D:prop>
                    </D:propfind>
                """
                async with session.request('PROPFIND', propfind_url, headers=headers, data=body) as resp:
                    xml_data = await resp.text()
                    chunk_hash = re.search(
                        r'<ChunkHash[^>]*>([^<]+)</ChunkHash>', xml_data).group(1)
                file_sha256.update(bytes.fromhex(chunk_hash))
                async with session.get(chunk_url) as resp:
                    chunk_data = await resp.read()
                    await session.request('PATCH', output_url, headers={
                        'Content-Type': 'application/octet-stream',
                        'Content-Length': str(len(chunk_data)),
                        'Content-Range': f'bytes */{chunk_info.file_size}'
                    }, data=chunk_data)
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


storages = {
    "local": SystemFileStorage,
    "s3": S3FileStorage,
    "onedrive": OneDriveFileStorage,
    "opendal": OpenDALFileStorage,
    "webdav": WebDAVFileStorage,
}
