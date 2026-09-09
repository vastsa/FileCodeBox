"""apps.base service layer: upload orchestration shared by share/chunk/presign.

Handlers in views.py keep HTTP concerns (form parsing, status codes, rate
limiting); this module owns the business workflow: path generation, storage
writes, share-record creation, and failure rollback.
"""
import os

from core.logger import logger
from core.storage import FileStorageInterface

from apps.base.models import FileCodes
from apps.base.utils import build_file_path, get_expire_info

import uuid


async def rollback_saved_file(
    storage: FileStorageInterface,
    file_path: str,
    uuid_file_name: str,
    *,
    context: str,
    upload_id: str | None = None,
) -> None:
    """Best-effort delete of a stored file after a failed upload workflow.

    Rollback failures are logged (with traceback) and swallowed: the original
    error must propagate; the file, if left behind, is cleaned by the expiry
    task once its orphaned record ages out.
    """
    try:
        await storage.delete_file(
            FileCodes(file_path=file_path, uuid_file_name=uuid_file_name)
        )
    except Exception:
        logger.warning(
            "%s：回滚删除已保存文件失败%s",
            context,
            f" upload_id={upload_id}" if upload_id else "",
            exc_info=True,
        )


class FileUploadService:
    """统一的文件上传服务"""

    @staticmethod
    async def generate_file_path(
        file_name: str, upload_id: str | None = None
    ) -> tuple[str, str, str, str, str]:
        """Delegates path generation to apps.base.utils.build_file_path."""
        return await build_file_path(file_name, upload_id or uuid.uuid4().hex)

    @staticmethod
    async def create_file_record(
        file_name: str,
        file_size: int,
        file_path: str,
        expire_value: int,
        expire_style: str,
        **extra_fields,
    ) -> str:
        """统一创建FileCodes记录，返回code"""
        expired_at, expired_count, used_count, code = await get_expire_info(
            expire_value, expire_style
        )
        prefix, suffix = os.path.splitext(file_name)

        await FileCodes.create(
            code=code,
            prefix=prefix,
            suffix=suffix,
            uuid_file_name=file_name,
            file_path=file_path,
            size=file_size,
            expired_at=expired_at,
            expired_count=expired_count,
            used_count=used_count,
            **extra_fields,
        )
        return code
