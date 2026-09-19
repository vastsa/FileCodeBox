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

from apps.base.upload_access import prepare_upload, upload_storage, create_upload_share, abort_access
from apps.base.file_validation import validate_upload_file
from apps.base.local_share import build_local_ref_download, is_local_ref
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


async def get_stored_download(file_code, file_storage: FileStorageInterface | None = None) -> StoredDownload:
    if is_local_ref(file_code):
        return build_local_ref_download(file_code)
    # NAS 引用沿用原逻辑；只有寄件分享需要覆盖默认存储。
    from apps.base.share_storage import storage_for_share
    storage = await storage_for_share(file_code, file_storage)
    return await storage.get_file_response(stored_file_of(file_code))


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
        access=None,
        **extra_fields,
    ) -> str:
        """统一创建FileCodes记录，返回code"""
        expired_at, expired_count, used_count, code = await get_expire_info(
            expire_value, expire_style
        )
        prefix, suffix = os.path.splitext(file_name)

        await create_upload_share(access,
            code=code, prefix=prefix, suffix=suffix, uuid_file_name=file_name,
            file_path=file_path, size=file_size, expired_at=expired_at,
            expired_count=expired_count, used_count=used_count, **extra_fields,
        )
        return code

    @staticmethod
    async def create_text_share(
        text: str, expire_value: int, expire_style: str, access=None
    ) -> str:
        """文本分享：配额预留 → 建分享记录 → 释放配额。"""
        text_size = len(text.encode("utf-8"))
        # 文本与普通发送一致存入取件表，并占用一次寄件授权。
        await prepare_upload(access, "Text", text_size, uuid.uuid4().hex)
        if access is not None and access.record is not None:
            access.record.stored_name = ""
            await access.record.save(update_fields=["stored_name"])
        token = access.record.token if access and access.record else f"text:{uuid.uuid4().hex}"
        await reserve_storage(token, text_size, ttl_seconds=300)
        try:
            expired_at, expired_count, used_count, code = await get_expire_info(
                expire_value, expire_style
            )
            await create_upload_share(access,
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
            await abort_access(access)
        return code

    @staticmethod
    async def create_file_share(
        file: UploadFile, *, size: int, expire_value: int, expire_style: str, access=None
    ) -> dict[str, str]:
        """文件分享：路径生成 → 配额预留 → 存储写入 → 建分享记录，失败回滚已存文件。"""
        path, suffix, prefix, uuid_file_name, save_path = (
            await FileUploadService.generate_file_path(file.filename or "")
        )
        # 寄件授权只覆盖路径与归属，保留普通上传校验和存储流程。
        _, delivery_path = await prepare_upload(access, file.filename, size, uuid.uuid4().hex)
        if delivery_path:
            save_path = delivery_path
            path, uuid_file_name = os.path.split(save_path)
        token = access.record.token if access and access.record else f"file:{uuid.uuid4().hex}"
        await reserve_storage(token, size, ttl_seconds=3600)
        storage = await upload_storage(access) if access and access.record else FileUploadService._storage()
        try:
            expired_at, expired_count, used_count, code = await get_expire_info(
                expire_value, expire_style
            )
            await storage.save_file(file.file, save_path, file.content_type)
            await create_upload_share(access,
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
            await abort_access(access)
        return {"code": code, "name": file.filename}

    @staticmethod
    async def complete_chunked_upload(
        upload_id: str, chunk_info: UploadChunk, expire_value: int, expire_style: str, access=None
    ) -> dict[str, str]:
        """分片合并：配额 → 完整性/大小校验 → 合并 → 建分享记录 → 清理分片。

        失败路径的配额释放与清理范围与原实现逐一对齐：
        完整性校验失败仅抛 400（预留由 TTL 兜底）；合并失败清理分片文件后抛 500。
        """
        storage = await upload_storage(access) if access and access.record else FileUploadService._storage()
        await reserve_storage(
            f"chunk:{upload_id}", chunk_info.file_size, ttl_seconds=chunk_reservation_ttl()
        )

        completed_chunks = await UploadChunk.filter(
            upload_id=upload_id, completed=True
        ).all()
        if len(completed_chunks) != chunk_info.total_chunks:
            raise HTTPException(400, "分片不完整")

        # 寄件预占按声明字节数计费；普通上传保持上游的分片容量规则。
        max_total_size = chunk_info.file_size if access and access.record else len(completed_chunks) * chunk_info.chunk_size
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
            await create_upload_share(access,
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
            try:
                await storage.clean_chunks(upload_id, save_path)
                await UploadChunk.filter(upload_id=upload_id).delete()
            except Exception:
                if not (access and access.record):
                    raise
                logger.warning("寄件分享已创建，分片清理稍后重试 upload_id=%s", upload_id, exc_info=True)
            await release_storage(f"chunk:{upload_id}")
            # 寄件存储名带唯一前缀，但发送结果仍展示原文件名。
            return {"code": code, "name": access.record.filename if access is not None and access.record is not None else safe_file_name}
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
        session: PresignUploadSession, file: UploadFile, access=None
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
        # 寄件必须与预占容量精确一致；普通代理保留上游的容差规则。
        mismatch = file_size != session.file_size if access and access.record else abs(file_size - session.file_size) > 1024
        if mismatch:
            raise HTTPException(400, "文件大小与声明不符")

        storage = await upload_storage(access) if access and access.record else FileUploadService._storage()
        try:
            await storage.save_file(file.file, session.save_path, file.content_type)
        except Exception as e:
            raise HTTPException(500, f"文件保存失败: {str(e)}")

        return await FileUploadService._commit_presign_record(
            session, file_size, storage, access=access,
            context="预签名代理上传：记录创建失败"
        )

    @staticmethod
    async def confirm_direct_upload(session: PresignUploadSession, access=None) -> str:
        """预签名直传确认：配额 → 文件存在性 → 建记录 → 会话清理。

        预留失败说明配额已耗尽，此时清理远端临时文件与会话后原样抛出。
        """
        if access and access.record:
            # 释放旧会话的上传次数；已签发的 URL 不能提前撤销，容量和清理记录保留到其过期。
            await abort_access(access, cleanup_after=session.expires_at)
            raise HTTPException(409, "旧寄件直传已停用，请重新上传；临时容量将在原会话过期后释放")
        try:
            await reserve_storage(
                f"presign:{session.upload_id}",
                session.file_size,
                ttl_seconds=PRESIGN_SESSION_EXPIRES,
            )
        except HTTPException:
            storage = await upload_storage(access) if access and access.record else FileUploadService._storage()
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

        storage = await upload_storage(access) if access and access.record else FileUploadService._storage()
        if not await storage.file_exists(session.save_path):
            raise HTTPException(404, "文件未上传或上传失败")

        return await FileUploadService._commit_presign_record(
            session, session.file_size, storage, access=access,
            context="预签名确认：记录创建失败"
        )

    @staticmethod
    async def _commit_presign_record(session, file_size, storage, *, access=None, context):
        """代理上传与直传共用记录提交、失败回滚及会话释放，避免两条路径行为分叉。"""
        try:
            code = await FileUploadService.create_file_record(
                session.file_name, file_size, os.path.dirname(session.save_path),
                session.expire_value, session.expire_style, access=access,
            )
        except Exception:
            await rollback_saved_file(
                storage, os.path.dirname(session.save_path), os.path.basename(session.save_path),
                context=context, upload_id=session.upload_id,
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
