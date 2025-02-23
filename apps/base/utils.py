import datetime
import hashlib
import os
import uuid

from fastapi import UploadFile, HTTPException
from typing import Optional, Tuple

from apps.base.dependencies import IPRateLimit
from apps.base.models import FileCodes
from core.settings import settings
from core.utils import get_random_num, get_random_string, max_save_times_desc


async def get_file_path_name(file: UploadFile) -> Tuple[str, str, str, str, str]:
    """获取文件路径和文件名"""
    today = datetime.datetime.now()
    storage_path = settings.storage_path.strip("/")  # 移除开头和结尾的斜杠
    file_uuid = uuid.uuid4().hex

    # 使用 UUID 作为子目录名
    base_path = f"share/data/{today.strftime('%Y/%m/%d')}/{file_uuid}"

    # 如果设置了存储路径，将其添加到基础路径中
    path = f"{storage_path}/{base_path}" if storage_path else base_path

    prefix, suffix = os.path.splitext(file.filename)
    # 保持原始文件名
    save_path = f"{path}/{file.filename}"
    return path, suffix, prefix, file.filename, save_path


async def get_chunk_file_path_name(file_name: str, upload_id: str) -> Tuple[str, str, str, str, str]:
    """获取切片文件的路径和文件名"""
    today = datetime.datetime.now()
    storage_path = settings.storage_path.strip("/")  # 移除开头和结尾的斜杠
    base_path = f"share/data/{today.strftime('%Y/%m/%d')}/{upload_id}"
    path = f"{storage_path}/{base_path}" if storage_path else base_path
    prefix, suffix = os.path.splitext(file_name)
    save_path = f"{path}/{prefix}{suffix}"
    return path, suffix, prefix, file_name, save_path


async def get_expire_info(
        expire_value: int, expire_style: str
) -> Tuple[Optional[datetime.datetime], int, int, str]:
    """获取过期信息"""
    expired_count, used_count = -1, 0
    now = datetime.datetime.now()
    code = None

    max_timedelta = (
        datetime.timedelta(seconds=settings.max_save_seconds)
        if settings.max_save_seconds > 0
        else datetime.timedelta(days=7)
    )
    detail = (
        await max_save_times_desc(settings.max_save_seconds)
        if settings.max_save_seconds > 0
        else "7天"
    )
    detail = f"限制最长时间为 {detail[0]}，可换用其他方式"

    expire_styles = {
        "day": lambda: now + datetime.timedelta(days=expire_value),
        "hour": lambda: now + datetime.timedelta(hours=expire_value),
        "minute": lambda: now + datetime.timedelta(minutes=expire_value),
        "count": lambda: (now + datetime.timedelta(days=1), expire_value),
        "forever": lambda: (None, None),  # 修改这里
    }

    if expire_style in expire_styles:
        result = expire_styles[expire_style]()
        if isinstance(result, tuple):
            expired_at, extra = result
            if expire_style == "count":
                expired_count = extra
            elif expire_style == "forever":
                code = await get_random_code(style="string")  # 移动到这里
        else:
            expired_at = result
        if expired_at and expired_at - now > max_timedelta:
            raise HTTPException(status_code=403, detail=detail)
    else:
        expired_at = now + datetime.timedelta(days=1)

    if not code:
        code = await get_random_code()

    return expired_at, expired_count, used_count, code


async def get_random_code(style="num") -> str:
    """获取随机字符串"""
    while True:
        code = await get_random_num() if style == "num" else await get_random_string()
        if not await FileCodes.filter(code=code).exists():
            return code


async def calculate_file_hash(file: UploadFile, chunk_size=1024 * 1024) -> str:
    sha = hashlib.sha256()
    await file.seek(0)
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        sha.update(chunk)
    await file.seek(0)
    return sha.hexdigest()


ip_limit = {
    "error": IPRateLimit(count=settings.uploadCount, minutes=settings.errorMinute),
    "upload": IPRateLimit(count=settings.errorCount, minutes=settings.errorMinute),
}
