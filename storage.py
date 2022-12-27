import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

import settings


class TencentCOS:
    def __init__(self, bucket: str, region: str, secret_id: str, secret_key: str):
        self.bucket = bucket
        self.region = region
        self.secret_id = secret_id
        self.secret_key = secret_key

    def upload(self, file: UploadFile, path: str) -> str:
        # 上传文件
        pass

    def download(self, path: str) -> BinaryIO:
        # 下载文件
        pass

    def delete(self, path: str) -> None:
        # 删除文件
        pass

    def get_url(self, path: str) -> str:
        # 获取文件访问链接
        pass


class FileSystemStorage:
    DATA_ROOT = Path(settings.DATA_ROOT)
    STATIC_URL = settings.STATIC_URL
    NAME = "filesystem"

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

    async def judge_delete_folder(self, filepath):
        currpath = os.path.dirname(filepath)
        if os.listdir(currpath):
            return
        while str(currpath) != (str(os.path.join(self.DATA_ROOT, 'upload'))):
            if not os.listdir(currpath):
                os.rmdir(os.path.abspath(currpath))
            currpath = os.path.dirname(currpath)


STORAGE_ENGINE = {
    "filesystem": FileSystemStorage
}
