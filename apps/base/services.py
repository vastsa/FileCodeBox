# @Time    : 2025/09/05 03:00
# @Author  : Jules
# @File    : services.py
# @Software: PyCharm

from fastapi import UploadFile, HTTPException
from typing import Tuple, Optional
import io

from apps.base.models import FileCodes
from apps.base.utils import get_expire_info, get_file_path_name
from core.storage import storages, FileStorageInterface
from core.settings import settings

async def create_file_code(
    file_bytes: bytes,
    filename: str,
    expire_value: int = 1,
    expire_style: str = "day",
) -> str:
    """
    Saves a file from bytes and creates a file code for it.
    This service is decoupled from FastAPI's UploadFile and can be used by the bot.

    :param file_bytes: The file content as bytes.
    :param filename: The original name of the file.
    :param expire_value: The expiration value (e.g., 1, 2, ...).
    :param expire_style: The expiration style ('day', 'hour', etc.).
    :return: The generated pickup code.
    """
    filesize = len(file_bytes)
    if filesize > settings.uploadSize:
        max_size_mb = settings.uploadSize / (1024 * 1024)
        raise ValueError(f"File size exceeds the limit of {max_size_mb:.2f} MB")

    if expire_style not in settings.expireStyle:
        raise ValueError("Invalid expiration style")

    # Create a mock UploadFile object that is compatible with the existing storage functions.
    class MockUploadFile:
        def __init__(self, content_bytes, name):
            self.file = io.BytesIO(content_bytes)
            self.filename = name
            # Mimic other necessary attributes of UploadFile
            self.content_type = "application/octet-stream"
            self.size = len(content_bytes)

        async def read(self) -> bytes:
            return self.file.read()

        async def seek(self, offset: int) -> None:
            self.file.seek(offset)

    upload_file_obj = MockUploadFile(file_bytes, filename)

    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
    path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(upload_file_obj)

    file_storage: FileStorageInterface = storages[settings.file_storage]()

    await file_storage.save_file(upload_file_obj, save_path)

    await FileCodes.create(
        code=code,
        prefix=prefix,
        suffix=suffix,
        uuid_file_name=uuid_file_name,
        file_path=path,
        size=filesize,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
    )

    return code


async def get_file_data_by_code(code: str) -> Optional[Tuple[bytes, str]]:
    """
    Retrieves file data and filename by its pickup code.

    :param code: The pickup code.
    :return: A tuple of (file_bytes, filename) or None if not found/expired.
    """
    file_code = await FileCodes.filter(code=code).first()
    if not file_code or await file_code.is_expired():
        return None

    file_storage: FileStorageInterface = storages[settings.file_storage]()

    response = await file_storage.get_file_response(file_code)

    # The response body from FileResponse can be an async generator.
    # We need to iterate over it to get the full content.
    content = b""
    if hasattr(response, "body_iterator"):
        async for chunk in response.body_iterator:
            content += chunk
    else:
        content = response.body

    filename = f"{file_code.prefix}{file_code.suffix}"

    # Update usage stats
    file_code.used_count += 1
    if file_code.expired_count > 0:
        file_code.expired_count -= 1
    await file_code.save()

    return content, filename
