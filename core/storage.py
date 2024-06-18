# @Time    : 2023/8/11 20:06
# @Author  : Lan
# @File    : storage.py
# @Software: PyCharm
from typing import Optional

import aiohttp
import asyncio
from pathlib import Path
import datetime
import io
import re
import sys
import aioboto3
from botocore.config import Config
from fastapi import HTTPException, Response, UploadFile
from core.response import APIResponse
from core.settings import data_root, settings
from apps.base.models import FileCodes
from core.utils import get_file_url
from fastapi.responses import FileResponse


class FileStorageInterface:
    _instance: Optional['FileStorageInterface'] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FileStorageInterface, cls).__new__(cls, *args, **kwargs)
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


class SystemFileStorage(FileStorageInterface):
    def __init__(self):
        self.chunk_size = 256 * 1024
        self.root_path = data_root

    def _save(self, file, save_path):
        with open(save_path, 'wb') as f:
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
            return APIResponse(code=404, detail='文件已过期删除')
        return FileResponse(file_path, filename=file_code.prefix + file_code.suffix)


class S3FileStorage(FileStorageInterface):
    def __init__(self):
        self.access_key_id = settings.s3_access_key_id
        self.secret_access_key = settings.s3_secret_access_key
        self.bucket_name = settings.s3_bucket_name
        self.s3_hostname = settings.s3_hostname
        self.region_name = settings.s3_region_name
        self.signature_version = settings.s3_signature_version
        self.endpoint_url = settings.s3_endpoint_url or f'https://{self.s3_hostname}'
        self.aws_session_token = settings.aws_session_token
        self.proxy = settings.s3_proxy
        self.session = aioboto3.Session(aws_access_key_id=self.access_key_id, aws_secret_access_key=self.secret_access_key)
        if not settings.s3_endpoint_url:
            self.endpoint_url = f'https://{self.s3_hostname}'
        else:
            # 如果提供了 s3_endpoint_url，则优先使用它
            self.endpoint_url = settings.s3_endpoint_url

    async def save_file(self, file: UploadFile, save_path: str):
        async with self.session.client("s3", endpoint_url=self.endpoint_url, aws_session_token=self.aws_session_token, region_name=self.region_name,
                                       config=Config(signature_version=self.signature_version)) as s3:
            await s3.put_object(Bucket=self.bucket_name, Key=save_path, Body=await file.read(), ContentType=file.content_type)

    async def delete_file(self, file_code: FileCodes):
        async with self.session.client("s3", endpoint_url=self.endpoint_url, region_name=self.region_name, config=Config(signature_version=self.signature_version)) as s3:
            await s3.delete_object(Bucket=self.bucket_name, Key=await file_code.get_file_path())

    async def get_file_response(self, file_code: FileCodes):
        try:
            filename = file_code.prefix + file_code.suffix
            async with self.session.client("s3", endpoint_url=self.endpoint_url, region_name=self.region_name, config=Config(signature_version=self.signature_version)) as s3:
                link = await s3.generate_presigned_url('get_object', Params={'Bucket': self.bucket_name, 'Key': await file_code.get_file_path()}, ExpiresIn=3600)
            tmp = io.BytesIO()
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    tmp.write(await resp.read())
            tmp.seek(0)
            content = tmp.read()
            tmp.close()
            return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode("latin-1")}"'})
        except Exception:
            raise HTTPException(status_code=503, detail='服务代理下载异常，请稍后再试')

    async def get_file_url(self, file_code: FileCodes):
        if file_code.prefix == '文本分享':
            return file_code.text
        if self.proxy:
            return await get_file_url(file_code.code)
        else:
            async with self.session.client("s3", endpoint_url=self.endpoint_url, region_name=self.region_name, config=Config(signature_version=self.signature_version)) as s3:
                result = await s3.generate_presigned_url('get_object', Params={'Bucket': self.bucket_name, 'Key': await file_code.get_file_path()}, ExpiresIn=3600)
                return result


class OneDriveFileStorage(FileStorageInterface):
    def __init__(self):
        try:
            import msal
            from office365.graph_client import GraphClient
            from office365.runtime.client_request_exception import ClientRequestException
        except ImportError:
            raise ImportError('请先安装`msal`和`Office365-REST-Python-Client`')
        self.msal = msal
        self.domain = settings.onedrive_domain
        self.client_id = settings.onedrive_client_id
        self.username = settings.onedrive_username
        self.password = settings.onedrive_password
        self.proxy = settings.onedrive_proxy
        self._ClientRequestException = ClientRequestException

        try:
            client = GraphClient(self.acquire_token_pwd)
            self.root_path = client.me.drive.root.get_by_path(settings.onedrive_root_path).get().execute_query()
        except ClientRequestException as e:
            if e.code == 'itemNotFound':
                client.me.drive.root.create_folder(settings.onedrive_root_path)
                self.root_path = client.me.drive.root.get_by_path(settings.onedrive_root_path).get().execute_query()
            else:
                raise e
        except Exception as e:
            raise Exception('OneDrive验证失败，请检查配置是否正确\n' + str(e))

    def acquire_token_pwd(self):
        authority_url = f'https://login.microsoftonline.com/{self.domain}'
        app = self.msal.PublicClientApplication(
            authority=authority_url,
            client_id=self.client_id
        )
        result = app.acquire_token_by_username_password(username=self.username,
                                                        password=self.password,
                                                        scopes=['https://graph.microsoft.com/.default'])
        return result

    def _get_path_str(self, path):
        if isinstance(path, str):
            path = path.replace('\\', '/').replace('//', '/').split('/')
        elif isinstance(path, Path):
            path = str(path).replace('\\', '/').replace('//', '/').split('/')
        else:
            raise TypeError('path must be str or Path')
        path[-1] = path[-1].split('.')[0]
        return '/'.join(path)

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
            if e.code == 'itemNotFound':
                pass
            else:
                raise e

    async def delete_file(self, file_code: FileCodes):
        await asyncio.to_thread(self._delete, await file_code.get_file_path())

    def _convert_link_to_download_link(self, link):
        p1 = re.search(r'https:\/\/(.+)\.sharepoint\.com', link).group(1)
        p2 = re.search(r'personal\/(.+)\/', link).group(1)
        p3 = re.search(rf'{p2}\/(.+)', link).group(1)
        return f'https://{p1}.sharepoint.com/personal/{p2}/_layouts/52/download.aspx?share={p3}'

    def _get_file_url(self, save_path, name):
        path = self._get_path_str(save_path)
        remote_file = self.root_path.get_by_path(path + '/' + name)
        expiration_datetime = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(hours=1)
        expiration_datetime = expiration_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        premission = remote_file.create_link("view", "anonymous", expiration_datetime=expiration_datetime).execute_query()
        return self._convert_link_to_download_link(premission.link.webUrl)

    async def get_file_response(self, file_code: FileCodes):
        try:
            filename = file_code.prefix + file_code.suffix
            link = await asyncio.to_thread(self._get_file_url, await file_code.get_file_path(), filename)
            tmp = io.BytesIO()
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    tmp.write(await resp.read())
            tmp.seek(0)
            content = tmp.read()
            tmp.close()
            return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{filename.encode("utf-8").decode("latin-1")}"'})
        except Exception:
            raise HTTPException(status_code=503, detail='服务代理下载异常，请稍后再试')

    async def get_file_url(self, file_code: FileCodes):
        if self.proxy:
            return await get_file_url(file_code.code)
        else:
            return await asyncio.to_thread(self._get_file_url, await file_code.get_file_path(), f'{file_code.prefix}{file_code.suffix}')


class OpenDALFileStorage(FileStorageInterface):
    def __init__(self):
        try:
            import opendal
        except ImportError:
            raise ImportError('请先安装 `opendal`, 例如: "pip install opendal"')
        self.service = settings.opendal_scheme
        service_settings = {}
        for key, value in settings.items():
            if key.startswith('opendal_' + self.service):
                setting_name = key.split('_', 2)[2]
                service_settings[setting_name] = value
        self.operator = opendal.AsyncOperator(settings.opendal_scheme, **service_settings)

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
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
            return Response(content, headers=headers, media_type="application/octet-stream")
        except Exception as e:
            print(e, file=sys.stderr)
            raise HTTPException(status_code=404, detail="文件已过期删除")


storages = {
    'local': SystemFileStorage,
    's3': S3FileStorage,
    'onedrive': OneDriveFileStorage,
    'opendal': OpenDALFileStorage,
}
