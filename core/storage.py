# @Time    : 2023/8/11 20:06
# @Author  : Lan
# @File    : storage.py
# @Software: PyCharm
import asyncio
import hashlib
import time
from pathlib import Path
import datetime
import re

import aioboto3
from fastapi import UploadFile
from core.settings import data_root, settings
from apps.base.models import FileCodes


class SystemFileStorage:
    def __init__(self):
        self.chunk_size = 256 * 1024
        self.root_path = data_root
        self.token = '123456'

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

    async def get_select_token(self, code):
        return hashlib.sha256(f"{code}{int(time.time() / 1000)}000{self.token}".encode()).hexdigest()

    async def get_file_url(self, file_code: FileCodes):
        return f'/share/download?key={await self.get_select_token(file_code.code)}&code={file_code.code}'


class S3FileStorage:
    def __init__(self):
        self.access_key_id = settings.s3_access_key_id
        self.secret_access_key = settings.s3_secret_access_key
        self.bucket_name = settings.s3_bucket_name
        self.endpoint_url = settings.s3_endpoint_url
        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key_id, aws_secret_access_key=self.secret_access_key
        )

    async def save_file(self, file: UploadFile, save_path: str):
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
            await s3.put_object(Bucket=self.bucket_name, Key=save_path, Body=await file.read(), ContentType=file.content_type)

    async def delete_file(self, file_code: FileCodes):
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
            await s3.delete_object(Bucket=self.bucket_name, Key=await file_code.get_file_path())

    async def get_file_url(self, file_code: FileCodes):
        if file_code.prefix == '文本分享':
            return file_code.text
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
            result = await s3.generate_presigned_url('get_object', Params={'Bucket': self.bucket_name, 'Key': await file_code.get_file_path()}, ExpiresIn=3600)
            return result


class OneDriveFileStorage:
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

    async def get_file_url(self, file_code: FileCodes):
        if file_code.prefix == '文本分享':
            return file_code.text
        result = await asyncio.to_thread(self._get_file_url, await file_code.get_file_path(), f'{file_code.prefix}{file_code.suffix}')
        return result


class FileStorageTemplate:
    def __init__(self):
        ...

    async def save_file(self, file: UploadFile, save_path: str):
        ...

    async def delete_file(self, file_code: FileCodes):
        ...

    async def get_file_url(self, file_code: FileCodes):
        ...


storages = {
    'local': SystemFileStorage,
    's3': S3FileStorage,
    'onedrive': OneDriveFileStorage,
}
file_storage = storages[settings.file_storage]()
