"""寄件专用存储边界：创建前检查配置，OneDrive 使用精确对象路径和私有下载。"""

import asyncio
import importlib.util
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

from fastapi import HTTPException
from starlette.background import BackgroundTask

from core.settings import settings
from core.storage import OneDriveFileStorage, StoredDownload, storages


def validate_storage_config(kind):
    """检查本机已有配置和可选依赖，不把缺少配置的后端包装成可用寄件码。"""
    required = {
        "local": [],
        "s3": ["s3_access_key_id", "s3_secret_access_key", "s3_bucket_name"],
        "webdav": ["webdav_url"],
        "onedrive": ["onedrive_domain", "onedrive_client_id", "onedrive_username", "onedrive_password", "onedrive_root_path"],
        "opendal": ["opendal_scheme"],
    }
    missing = [key for key in required[kind] if not str(getattr(settings, key, "") or "").strip()]
    if missing:
        raise HTTPException(422, f"请先在站点后台配置 {kind}：" + "、".join(missing))
    if kind in {"s3", "webdav"}:
        url = settings.webdav_url if kind == "webdav" else (settings.s3_endpoint_url or f"https://{settings.s3_hostname}")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise HTTPException(422, f"请先配置有效的 {kind} 服务地址")
    modules = {"onedrive": ["msal", "office365"], "opendal": ["opendal"]}
    if any(importlib.util.find_spec(module) is None for module in modules.get(kind, [])):
        packages = "msal 和 Office365-REST-Python-Client" if kind == "onedrive" else "opendal"
        raise HTTPException(422, "服务器缺少可选存储依赖，请先安装 " + packages)
    if kind == "opendal":
        prefix = "opendal_" + str(settings.opendal_scheme) + "_"
        if settings.opendal_scheme == "memory" or not any(key.startswith(prefix) and value for key, value in settings.items()):
            raise HTTPException(422, "请先配置 OpenDAL 持久化存储参数，寄件不支持 memory 后端")


async def get_storage(kind):
    # OneDrive 构造器会请求 Graph，放入线程以免阻塞其他用户的上传与租约心跳。
    if kind == "onedrive":
        return await asyncio.to_thread(DeliveryOneDriveStorage)
    return storages[kind]()


class DeliveryOneDriveStorage(OneDriveFileStorage):
    """独立适配已有 SDK，避免旧分享目录约定及匿名分享链接影响私有寄件。"""

    async def save_file(self, stream, save_path, content_type=None):
        # SDK 的 upload_file 同时支持小文件和大文件上传会话，调用对象必须是父目录。
        def upload():
            path = PurePosixPath(save_path)
            folder = self.root_path
            for part in path.parent.parts:
                try:
                    folder = folder.get_by_path(part).get().execute_query()
                except self._ClientRequestException as exc:
                    if exc.code != "itemNotFound":
                        raise
                    parent = folder
                    try:
                        parent.create_folder(part).execute_query()
                    except self._ClientRequestException as conflict:
                        if conflict.code not in {"nameAlreadyExists", "itemAlreadyExists"}:
                            raise
                    # SDK 可能对同名目录自动改名；重新按指定路径读取，避免文件落到别处。
                    folder = parent.get_by_path(part).get().execute_query()
            with tempfile.TemporaryDirectory(prefix="fr-") as temporary:
                local = Path(temporary) / path.name
                with local.open("wb") as target:
                    shutil.copyfileobj(stream, target, length=256 * 1024)
                folder.upload_file(str(local)).execute_query()
        await asyncio.to_thread(upload)

    def _delete(self, save_path):
        # 删除完整文件对象，不截去扩展名，也不递归删除存放其他寄件的目标目录。
        try:
            self.root_path.get_by_path(str(save_path).replace("\\", "/")).delete_object().execute_query()
        except self._ClientRequestException as exc:
            if exc.code != "itemNotFound":
                raise

    async def get_file_response(self, file_code):
        # 通过已认证 Graph 会话下载到临时文件，不创建 anonymous 分享权限。
        temporary = tempfile.TemporaryFile(mode="w+b")
        def fetch():
            self.root_path.get_by_path(file_code.get_file_path()).download_session(temporary).execute_query()
            size = temporary.tell()
            temporary.seek(0)
            return size
        downloading = asyncio.create_task(asyncio.to_thread(fetch))
        try:
            size = await asyncio.shield(downloading)
        except BaseException:
            # 线程操作结束后再关闭句柄，避免断线导致后台线程写入已关闭文件。
            try:
                await downloading
            finally:
                temporary.close()
            raise
        async def stream():
            try:
                while chunk := await asyncio.to_thread(temporary.read, 256 * 1024):
                    yield chunk
            finally:
                temporary.close()
        name = file_code.prefix + file_code.suffix
        return StoredDownload(
            filename=name,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}", "Content-Length": str(size)},
            stream_factory=stream, background=BackgroundTask(temporary.close),
        )
