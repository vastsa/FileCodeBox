"""寄件仅验证已配置的存储类型，文件读写直接复用上游驱动。"""

from urllib.parse import urlparse
from fastapi import HTTPException
from core.settings import settings
from core.storage import storages


def validate_storage_config(kind):
    """复用站点存储配置，缺少必要配置时不发放新的寄件授权。"""
    required = {
        "local": [],
        "s3": ["s3_access_key_id", "s3_secret_access_key", "s3_bucket_name"],
        "webdav": ["webdav_url"],
    }
    if kind not in {"local", "s3", "webdav"}:
        raise HTTPException(422, "寄件仅支持本地、S3 和 WebDAV 存储")
    missing = [key for key in required[kind] if not str(getattr(settings, key, "") or "").strip()]
    if missing:
        raise HTTPException(422, f"请先在站点后台配置 {kind}：" + "、".join(missing))
    if kind in {"s3", "webdav"}:
        url = settings.webdav_url if kind == "webdav" else (settings.s3_endpoint_url or f"https://{settings.s3_hostname}")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise HTTPException(422, f"请先配置有效的 {kind} 服务地址")


async def get_storage(kind):
    """不包装或重写驱动行为；历史记录读取也交由已有驱动处理。"""
    return storages[kind]()
