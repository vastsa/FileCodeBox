import datetime
import hashlib
import os
import uuid
from urllib.parse import unquote

from fastapi import UploadFile, HTTPException
from typing import Optional, Tuple

from apps.base.dependencies import IPRateLimit
from apps.base.models import FileCodes
from core.settings import settings
from core.utils import (
    get_random_num,
    get_random_string,
    max_save_times_desc,
    sanitize_filename,
    get_now,
)


def validate_expire_style(expire_style: str) -> str:
    """校验过期方式是否在管理员配置的白名单内。"""
    if expire_style not in settings.expireStyle:
        raise HTTPException(status_code=400, detail="过期时间类型错误")
    return expire_style


async def get_file_path_name(file: UploadFile) -> Tuple[str, str, str, str, str]:
    today = await get_now()
    storage_path = settings.storage_path.strip("/")
    file_uuid = uuid.uuid4().hex
    filename = await sanitize_filename(unquote(file.filename or ""))
    base_path = f"share/data/{today.strftime('%Y/%m/%d')}/{file_uuid}"
    path = f"{storage_path}/{base_path}" if storage_path else base_path
    prefix, suffix = os.path.splitext(filename)
    save_path = f"{path}/{filename}"
    return path, suffix, prefix, filename, save_path


async def get_chunk_file_path_name(
    file_name: str, upload_id: str
) -> Tuple[str, str, str, str, str]:
    today = await get_now()
    storage_path = settings.storage_path.strip("/")
    base_path = f"share/data/{today.strftime('%Y/%m/%d')}/{upload_id}"
    path = f"{storage_path}/{base_path}" if storage_path else base_path
    prefix, suffix = os.path.splitext(file_name)
    save_path = f"{path}/{prefix}{suffix}"
    return path, suffix, prefix, file_name, save_path


async def get_expire_info(
    expire_value: int, expire_style: str
) -> Tuple[Optional[datetime.datetime], int, int, str]:
    expired_count, used_count = -1, 0
    now = await get_now()
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
        "forever": lambda: (None, None),
    }

    if expire_style in expire_styles:
        result = expire_styles[expire_style]()
        if isinstance(result, tuple):
            expired_at, extra = result
            if expire_style == "count":
                expired_count = extra
        else:
            expired_at = result
        if expired_at and expired_at - now > max_timedelta:
            raise HTTPException(status_code=403, detail=detail)
    else:
        expired_at = now + datetime.timedelta(days=1)

    if not code:
        code = await get_random_code()

    return expired_at, expired_count, used_count, code


def get_code_generate_type() -> str:
    code_generate_type = getattr(settings, "code_generate_type", "secret")
    if code_generate_type in {"secret", "string"}:
        return "secret"
    return "number"


async def get_random_code(style: str | None = None) -> str:
    code_style = style or get_code_generate_type()
    if code_style == "num":
        code_style = "number"
    if code_style == "string":
        code_style = "secret"

    while True:
        code = (
            await get_random_num()
            if code_style == "number"
            else await get_random_string()
        )
        if not await FileCodes.filter(code=code).exists():
            return str(code)


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
    "error": IPRateLimit(count=settings.errorCount, minutes=settings.errorMinute),
    "metadata": IPRateLimit(count=settings.errorCount, minutes=settings.errorMinute),
    "upload": IPRateLimit(count=settings.uploadCount, minutes=settings.uploadMinute),
    "login": IPRateLimit(count=settings.loginCount, minutes=settings.loginMinute),
}
