# @Time    : 2023/8/11 20:06
# @Author  : Lan
# @File    : storage.py
# @Software: PyCharm
import asyncio
import aioboto3
from fastapi import UploadFile
from pathlib import Path

from apps.base.models import FileCodes


class SystemFileStorage:
    def __init__(self):
        self.chunk_size = 256 * 1024
        self.root_path = Path('./data')

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
        return f"/api/select?code={file_code.code}"


class S3FileStorage:
    def __init__(self):
        self.access_key_id = ''
        self.secret_access_key = ''
        self.bucket_name = ''
        self.endpoint_url = ''
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
        async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
            result = await s3.generate_presigned_url('get_object', Params={'Bucket': self.bucket_name, 'Key': await file_code.get_file_path()}, ExpiresIn=3600)
            return result


file_storage = SystemFileStorage()
