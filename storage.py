import os
import asyncio
import datetime
from pathlib import Path

import settings


class FileSystemStorage:
    DATA_ROOT = Path(settings.DATA_ROOT)
    STATIC_URL = settings.STATIC_URL
    NAME = "filesystem"

    async def get_filepath(self, path):
        return self.DATA_ROOT / path.lstrip(self.STATIC_URL + '/')

    def _save(self, filepath, file_bytes):
        with open(filepath, 'wb') as f:
            f.write(file_bytes)

    async def save_file(self, file, file_bytes, key):
        now = datetime.datetime.now()
        path = self.DATA_ROOT / f"upload/{now.year}/{now.month}/{now.day}/"
        ext = file.filename.split('.')[-1]
        name = f'{key}.{ext}'
        if not path.exists():
            path.mkdir(parents=True)
        filepath = path / name
        await asyncio.to_thread(self._save, filepath, file_bytes)
        text = f"{self.STATIC_URL}/{filepath.relative_to(self.DATA_ROOT)}"
        return text

    async def delete_file(self, file):
        # 是文件就删除
        if file['type'] != 'text':
            filepath = self.DATA_ROOT / file['text'].lstrip(self.STATIC_URL + '/')
            await asyncio.to_thread(os.remove, filepath)

    async def delete_files(self, files):
        for file in files:
            if file['type'] != 'text':
                await self.delete_file(file)


STORAGE_ENGINE = {
    "filesystem": FileSystemStorage
}
