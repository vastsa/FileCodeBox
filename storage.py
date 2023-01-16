import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from fastapi import UploadFile
import settings

if settings.STORAGE_ENGINE == "aliyunsystem":
    import oss2


class AliyunFileStore:
    def __init__(self):
        auth = oss2.Auth(settings.KeyId, settings.KeySecret)
        self.bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.BUCKET_NAME)

    def upload_file(self, upload_filepath, remote_filepath):
        self.bucket.put_object_from_file(remote_filepath, upload_filepath)

    async def get_text(self, file: UploadFile, key: str):
        ext = file.filename.split('.')[-1]
        now = datetime.now()
        path = f"FileCodeBox/upload/{now.year}/{now.month}/{now.day}"
        text = f"{path}/{f'{key}.{ext}'}"
        return text

    async def get_filepath(self, text: str):
        text = text.strip(f"https://{settings.BUCKET_NAME}.{settings.OSS_ENDPOINT}/")
        url = self.bucket.sign_url('GET', text, settings.ACCESSTIME, slash_safe=True)
        return url

    @staticmethod
    async def get_size(file: UploadFile):
        f = file.file
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0, os.SEEK_SET)
        return size

    @staticmethod
    def _save(filepath, file: BinaryIO):
        with open(filepath, 'wb') as f:
            chunk_size = 256 * 1024
            chunk = file.read(chunk_size)
            while chunk:
                f.write(chunk)
                chunk = file.read(chunk_size)

    async def save_file(self, file: UploadFile, remote_filepath: str):
        now = int(datetime.now().timestamp())
        upload_filepath = settings.DATA_ROOT+str(now)
        await asyncio.to_thread(self._save, upload_filepath, file.file)
        self.upload_file(upload_filepath,remote_filepath)
        await asyncio.to_thread(os.remove,upload_filepath)

    async def delete_files(self, texts):
        tasks = [self.delete_file(text) for text in texts]
        await asyncio.gather(*tasks)

    async def delete_file(self, text: str):
        text = text.strip(f"https://{settings.BUCKET_NAME}.{settings.OSS_ENDPOINT}/")
        self.bucket.delete_object(text)


class FileSystemStorage:
    def __init__(self):
        self.DATA_ROOT = Path(settings.DATA_ROOT)
        self.STATIC_URL = settings.STATIC_URL
        self.NAME = "filesystem"

    async def get_filepath(self, text: str):
        return self.DATA_ROOT / text.lstrip(self.STATIC_URL + '/')

    async def get_text(self, file: UploadFile, key: str):
        ext = file.filename.split('.')[-1]
        now = datetime.now()
        path = self.DATA_ROOT / f"upload/{now.year}/{now.month}/{now.day}/"
        if not path.exists():
            path.mkdir(parents=True)
        text = f"{self.STATIC_URL}/{(path / f'{key}.{ext}').relative_to(self.DATA_ROOT)}"
        return text

    @staticmethod
    async def get_size(file: UploadFile):
        f = file.file
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0, os.SEEK_SET)
        return size

    @staticmethod
    def _save(filepath, file: BinaryIO):
        with open(filepath, 'wb') as f:
            chunk_size = 256 * 1024
            chunk = file.read(chunk_size)
            while chunk:
                f.write(chunk)
                chunk = file.read(chunk_size)

    async def save_file(self, file: UploadFile, text: str):
        filepath = await self.get_filepath(text)
        await asyncio.to_thread(self._save, filepath, file.file)

    async def delete_file(self, text: str):
        filepath = await self.get_filepath(text)
        if filepath.exists():
            await asyncio.to_thread(os.remove, filepath)
            await asyncio.to_thread(self.judge_delete_folder, filepath)

    async def delete_files(self, texts):
        tasks = [self.delete_file(text) for text in texts]
        await asyncio.gather(*tasks)

    def judge_delete_folder(self, filepath):
        current = filepath.parent
        while current != self.DATA_ROOT:
            if not list(current.iterdir()):
                os.rmdir(current)
                current = current.parent
            else:
                break


STORAGE_ENGINE = {
    "filesystem": FileSystemStorage,
    "aliyunsystem": AliyunFileStore
}
