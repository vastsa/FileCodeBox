import os
import time

from core.response import APIResponse
from core.storage import FileStorageInterface, storages
from core.settings import settings
from apps.base.models import FileCodes, KeyValue
from apps.base.utils import get_expire_info, get_file_path_name
from fastapi import HTTPException
from core.settings import data_root


class FileService:
    def __init__(self):
        self.file_storage: FileStorageInterface = storages[settings.file_storage]()

    async def delete_file(self, file_id: int):
        file_code = await FileCodes.get(id=file_id)
        await self.file_storage.delete_file(file_code)
        await file_code.delete()

    async def list_files(self, page: int, size: int, keyword: str = ""):
        offset = (page - 1) * size
        files = (
            await FileCodes.filter(prefix__icontains=keyword).limit(size).offset(offset)
        )
        total = await FileCodes.filter(prefix__icontains=keyword).count()
        return files, total

    async def download_file(self, file_id: int):
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")
        if file_code.text:
            return APIResponse(detail=file_code.text)
        else:
            return await self.file_storage.get_file_response(file_code)

    async def share_local_file(self, item):
        local_file = LocalFileClass(item.filename)
        if not await local_file.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        text = await local_file.read()
        expired_at, expired_count, used_count, code = await get_expire_info(
            item.expire_value, item.expire_style
        )
        path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(item)

        await self.file_storage.save_file(text, save_path)

        await FileCodes.create(
            code=code,
            prefix=prefix,
            suffix=suffix,
            uuid_file_name=uuid_file_name,
            file_path=path,
            size=local_file.size,
            expired_at=expired_at,
            expired_count=expired_count,
            used_count=used_count,
        )

        return {
            "code": code,
            "name": local_file.file,
        }


class ConfigService:
    def get_config(self):
        return settings.items()

    async def update_config(self, data: dict):
        admin_token = data.get("admin_token")
        if admin_token is None or admin_token == "":
            raise HTTPException(status_code=400, detail="管理员密码不能为空")

        for key, value in data.items():
            if key not in settings.default_config:
                continue
            if key in [
                "errorCount",
                "errorMinute",
                "max_save_seconds",
                "onedrive_proxy",
                "openUpload",
                "port",
                "s3_proxy",
                "uploadCount",
                "uploadMinute",
                "uploadSize",
            ]:
                data[key] = int(value)
            elif key in ["opacity"]:
                data[key] = float(value)
            else:
                data[key] = value

        await KeyValue.filter(key="settings").update(value=data)
        for k, v in data.items():
            settings.__setattr__(k, v)


class LocalFileService:
    async def list_files(self):
        files = []
        if not os.path.exists(data_root / "local"):
            os.makedirs(data_root / "local")
        for file in os.listdir(data_root / "local"):
            files.append(LocalFileClass(file))
        return files

    async def delete_file(self, filename: str):
        file = LocalFileClass(filename)
        if await file.exists():
            await file.delete()
            return "删除成功"
        raise HTTPException(status_code=404, detail="文件不存在")


class LocalFileClass:
    def __init__(self, file):
        self.file = file
        self.path = data_root / "local" / file
        self.ctime = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getctime(self.path))
        )
        self.size = os.path.getsize(self.path)

    async def read(self):
        return open(self.path, "rb")

    async def write(self, data):
        with open(self.path, "w") as f:
            f.write(data)

    async def delete(self):
        os.remove(self.path)

    async def exists(self):
        return os.path.exists(self.path)
