"""apps.base service layer: upload orchestration shared by share/chunk/presign.

Handlers in views.py keep HTTP concerns (form parsing, session lookup, status
codes for malformed requests, rate limiting); this module owns the business
workflow: quota reservation, storage writes, share-record creation, and
failure rollback/cleanup.
"""
import os

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from core.logger import logger
from core.settings import settings
from core.storage import FileStorageInterface, StoredDownload, StoredFile, storages

from apps.base.file_validation import validate_upload_file
from apps.base.models import FileCodes, PresignUploadSession, UploadChunk
from apps.base.quota import release_storage, reserve_storage
from apps.base.utils import build_file_path, get_expire_info

import uuid

# 预签名上传会话有效期（秒）
PRESIGN_SESSION_EXPIRES = 900  # 15分钟


def stored_file_of(code: FileCodes) -> StoredFile:
    """Adapter: project an ORM FileCodes row onto the storage-layer contract."""
    return StoredFile(
        file_path=code.file_path,
        uuid_file_name=code.uuid_file_name,
        code=code.code,
        prefix=code.prefix,
        suffix=code.suffix,
        text=code.text or "",
    )


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
            StoredFile(file_path=file_path, uuid_file_name=uuid_file_name)
        )
    except Exception:
        logger.warning(
            "%s：回滚删除已保存文件失败%s",
            context,
            f" upload_id={upload_id}" if upload_id else "",
            exc_info=True,
        )


async def validate_file_size(file: UploadFile, max_size: int) -> int:
    """Return the upload's size, rejecting anything above max_size."""
    size = file.size
    if size is None:
        await file.seek(0, 2)  # type: ignore[arg-type]
        size = file.file.tell()
        await file.seek(0)
    if size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"大小超过限制,最大为{max_size_mb:.2f} MB"
        )
    return size


def chunk_reservation_ttl() -> int:
    ttl = max(1, int(getattr(settings, "chunk_expire_hours", 24))) * 3600
    return ttl


class FileUploadService:
    """统一的文件上传服务"""

    @staticmethod
    def _storage() -> FileStorageInterface:
        return storages[settings.file_storage]()

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

    @staticmethod
    async def create_text_share(
        text: str, expire_value: int, expire_style: str
    ) -> str:
        """文本分享：配额预留 → 建分享记录 → 释放配额。"""
        text_size = len(text.encode("utf-8"))
        token = f"text:{uuid.uuid4().hex}"
        await reserve_storage(token, text_size, ttl_seconds=300)
        try:
            expired_at, expired_count, used_count, code = await get_expire_info(
                expire_value, expire_style
            )
            await FileCodes.create(
                code=code,
                text=text,
                expired_at=expired_at,
                expired_count=expired_count,
                used_count=used_count,
                size=text_size,
                prefix="Text",
            )
        finally:
            await release_storage(token)
        return code

    @staticmethod
    async def create_file_share(
        file: UploadFile, *, size: int, expire_value: int, expire_style: str
    ) -> dict[str, str]:
        """文件分享：路径生成 → 配额预留 → 存储写入 → 建分享记录，失败回滚已存文件。"""
        path, suffix, prefix, uuid_file_name, save_path = (
            await FileUploadService.generate_file_path(file.filename or "")
        )
        token = f"file:{uuid.uuid4().hex}"
        await reserve_storage(token, size, ttl_seconds=3600)
        storage = FileUploadService._storage()
        try:
            expired_at, expired_count, used_count, code = await get_expire_info(
                expire_value, expire_style
            )
            await storage.save_file(file.file, save_path, file.content_type)
            await FileCodes.create(
                code=code,
                prefix=prefix,
                suffix=suffix,
                uuid_file_name=uuid_file_name,
                file_path=path,
                size=size,
                expired_at=expired_at,
                expired_count=expired_count,
                used_count=used_count,
            )
        except Exception:
            await rollback_saved_file(
                storage, path, uuid_file_name, context="分享上传"
            )
            raise
        finally:
            await release_storage(token)
        return {"code": code, "name": file.filename}

    @staticmethod
    async def complete_chunked_upload(
        upload_id: str, chunk_info: UploadChunk, expire_value: int, expire_style: str
    ) -> dict[str, str]:
        """分片合并：配额 → 完整性/大小校验 → 合并 → 建分享记录 → 清理分片。

        失败路径的配额释放与清理范围与原实现逐一对齐：
        完整性校验失败仅抛 400（预留由 TTL 兜底）；合并失败清理分片文件后抛 500。
        """
        storage = FileUploadService._storage()
        await reserve_storage(
            f"chunk:{upload_id}", chunk_info.file_size, ttl_seconds=chunk_reservation_ttl()
        )

        completed_chunks = await UploadChunk.filter(
            upload_id=upload_id, completed=True
        ).all()
        if len(completed_chunks) != chunk_info.total_chunks:
            raise HTTPException(400, "分片不完整")

        # 用分片数 * chunk_size 校验最大可能大小
        max_total_size = len(completed_chunks) * chunk_info.chunk_size
        if max_total_size > settings.upload_size:
            save_path = chunk_info.save_path
            if save_path:
                try:
                    await storage.clean_chunks(upload_id, save_path)
                except Exception:
                    logger.warning(
                        "分片超限中止：清理分片文件失败 upload_id=%s",
                        upload_id,
                        exc_info=True,
                    )
            await UploadChunk.filter(upload_id=upload_id).delete()
            await release_storage(f"chunk:{upload_id}")
            max_size_mb = settings.upload_size / (1024 * 1024)
            raise HTTPException(
                403, f"实际上传大小超过限制，最大为 {max_size_mb:.2f} MB"
            )

        save_path = chunk_info.save_path
        path = os.path.dirname(save_path) if save_path else ""
        safe_file_name = os.path.basename(save_path) if save_path else ""
        prefix, suffix = os.path.splitext(safe_file_name)

        try:
            records = {r.chunk_index: r for r in completed_chunks}
            _, file_hash = await storage.merge_chunks(
                upload_id,
                chunk_info.total_chunks,
                chunk_info.chunk_size,
                save_path,
                records,
            )
            expired_at, expired_count, used_count, code = await get_expire_info(
                expire_value, expire_style
            )
            await FileCodes.create(
                code=code,
                file_hash=file_hash,  # 使用合并后计算的哈希
                is_chunked=True,
                upload_id=upload_id,
                size=chunk_info.file_size,
                expired_at=expired_at,
                expired_count=expired_count,
                used_count=used_count,
                file_path=path,
                uuid_file_name=safe_file_name,
                prefix=prefix,
                suffix=suffix,
            )
            await storage.clean_chunks(upload_id, save_path)
            await UploadChunk.filter(upload_id=upload_id).delete()
            await release_storage(f"chunk:{upload_id}")
            return {"code": code, "name": safe_file_name}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            # 合并失败时清理临时文件
            try:
                await storage.clean_chunks(upload_id, save_path)
            except Exception:
                logger.warning(
                    "分片合并失败：清理临时分片文件失败 upload_id=%s",
                    upload_id,
                    exc_info=True,
                )
            raise HTTPException(500, f"文件合并失败: {str(e)}")

    @staticmethod
    async def commit_proxy_upload(
        session: PresignUploadSession, file: UploadFile
    ) -> str:
        """预签名代理上传：配额 → 大小/类型/一致性校验 → 转存 → 建记录 → 会话清理。

        校验失败不释放预留（与原实现一致，由 TTL 兜底）。
        """
        await reserve_storage(
            f"presign:{session.upload_id}",
            session.file_size,
            ttl_seconds=PRESIGN_SESSION_EXPIRES,
        )

        file_size = await validate_file_size(file, settings.upload_size)
        await validate_upload_file(file)
        if abs(file_size - session.file_size) > 1024:
            raise HTTPException(400, "文件大小与声明不符")

        storage = FileUploadService._storage()
        try:
            await storage.save_file(file.file, session.save_path, file.content_type)
        except Exception as e:
            raise HTTPException(500, f"文件保存失败: {str(e)}")

        try:
            code = await FileUploadService.create_file_record(
                session.file_name,
                file_size,
                os.path.dirname(session.save_path),
                session.expire_value,
                session.expire_style,
            )
        except Exception:
            await rollback_saved_file(
                storage,
                os.path.dirname(session.save_path),
                os.path.basename(session.save_path),
                context="预签名代理上传：记录创建失败",
                upload_id=session.upload_id,
            )
            raise

        await session.delete()
        await release_storage(f"presign:{session.upload_id}")
        return code

    @staticmethod
    async def confirm_direct_upload(session: PresignUploadSession) -> str:
        """预签名直传确认：配额 → 文件存在性 → 建记录 → 会话清理。

        预留失败说明配额已耗尽，此时清理远端临时文件与会话后原样抛出。
        """
        try:
            await reserve_storage(
                f"presign:{session.upload_id}",
                session.file_size,
                ttl_seconds=PRESIGN_SESSION_EXPIRES,
            )
        except HTTPException:
            storage = FileUploadService._storage()
            try:
                if await storage.file_exists(session.save_path):
                    await storage.delete_file(
                        StoredFile(
                            file_path=os.path.dirname(session.save_path),
                            uuid_file_name=os.path.basename(session.save_path),
                        )
                    )
            finally:
                await session.delete()
                await release_storage(f"presign:{session.upload_id}")
            raise

        storage = FileUploadService._storage()
        if not await storage.file_exists(session.save_path):
            raise HTTPException(404, "文件未上传或上传失败")

        try:
            code = await FileUploadService.create_file_record(
                session.file_name,
                session.file_size,
                os.path.dirname(session.save_path),
                session.expire_value,
                session.expire_style,
            )
        except Exception:
            await rollback_saved_file(
                storage,
                os.path.dirname(session.save_path),
                os.path.basename(session.save_path),
                context="预签名确认：记录创建失败",
                upload_id=session.upload_id,
            )
            raise

        await session.delete()
        await release_storage(f"presign:{session.upload_id}")
        return code


def response_from_download(download: StoredDownload):
    """Build the starlette Response for a StoredDownload (view-layer duty)."""
    if download.path is not None:
        return FileResponse(
            download.path,
            media_type=download.media_type,
            headers=download.headers,
            filename=download.filename,
        )
    if download.content is not None:
        return Response(
            download.content, media_type=download.media_type, headers=download.headers
        )
    return StreamingResponse(
        download.stream_factory(),
        media_type=download.media_type,
        headers=download.headers,
        background=download.background,
    )
