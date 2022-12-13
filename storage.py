import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

import settings


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
        filepath = path / f'{key}.{ext}'
        text = f"{self.STATIC_URL}/{filepath.relative_to(self.DATA_ROOT)}"
        return text

    async def get_size(self, file: UploadFile):
        f = file.file
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0, os.SEEK_SET)
        return size

    def _save(self, filepath, file: BinaryIO):
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
        await asyncio.to_thread(os.remove, filepath)

    async def delete_files(self, texts):
        tasks = [self.delete_file(text) for text in texts]
        await asyncio.gather(*tasks)


STORAGE_ENGINE = {
    "filesystem": FileSystemStorage
}
