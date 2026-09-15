"""寄件业务：独立权限、数据库次数预占、存储落盘和失败回收。"""

import asyncio
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.expressions import F
from tortoise.transactions import in_transaction

from apps.admin.dependencies import create_token, verify_token
from apps.base.file_validation import validate_upload_file
from apps.base.models import DeliveryCode, DeliveryFile, FileCodes, KeyValue, UploadChunk, PresignUploadSession, StorageReservation
from apps.base.utils import get_expire_info, validate_expire_style
from apps.base.quota import _sql_placeholders, reserve_storage
from apps.delivery.storage import get_storage, validate_storage_config
from core.logger import logger
from core.settings import settings
from core.storage import StoredFile
from core.utils import get_now, sanitize_filename

TOKEN_TTL = 900
STALE_SECONDS = 7200


def code_digest(code: str) -> str:
    """校验使用带服务端密钥的摘要，与管理员读取原文的用途分开。"""
    secret = str(settings.jwt_secret)
    if not secret:
        raise HTTPException(503, "系统签名密钥尚未初始化")
    return hmac.new(secret.encode(), ("delivery-code:" + code).encode(), hashlib.sha256).hexdigest()


def upload_identity(authorization: str | None) -> int:
    """只接受用途为 delivery 的凭证；管理员 token 也不能被误当作寄件授权。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先验证寄件码")
    try:
        payload = verify_token(authorization[7:])
        if payload.get("purpose") != "delivery" or payload.get("is_admin"):
            raise ValueError("凭证用途错误")
        return int(payload["delivery_id"])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(401, "寄件凭证无效或已过期，请重新验证寄件码") from None


async def active_code(code_id: int) -> DeliveryCode:
    record = await DeliveryCode.filter(id=code_id, owner_id="admin", enabled=True, deleted=False).first()
    if not record or record.expires_at <= await get_now():
        raise HTTPException(403, "寄件码无效、已过期或已停用")
    return record


async def create_code(data):
    """创建时保存原文，便于管理员后续查看；访客响应仍不提供任何口令列表。"""
    validate_storage_config(data.storage_type)
    code = data.code or "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(16))
    try:
        record = await DeliveryCode.create(
            code_digest=code_digest(code), code_value=code, name=data.name, owner_id="admin",
            storage_type=data.storage_type, target_path=data.target_path,
            expires_at=data.expires_at, max_uploads=data.max_uploads,
        )
    except IntegrityError:
        raise HTTPException(409, "该寄件码已被使用，请设置其他口令") from None
    return {"item": await code_summary(record), "code": code}


async def code_summary(record):
    """仅供已鉴权的后台读取状态和口令原文，不返回摘要或存储密钥。"""
    now = await get_now()
    state = "active"
    if record.deleted:
        state = "deleted"
    elif not record.enabled:
        state = "disabled"
    elif record.expires_at <= now:
        state = "expired"
    elif record.used_count >= record.max_uploads:
        state = "exhausted"
    return {
        "id": record.id, "name": record.name, "storage_type": record.storage_type,
        "code": record.code_value,
        "target_path": record.target_path, "expires_at": record.expires_at,
        "max_uploads": record.max_uploads, "used_count": record.used_count,
        "reserved_count": record.reserved_count, "enabled": record.enabled,
        "deleted": record.deleted, "status": state, "created_at": record.created_at,
        "remaining": max(0, record.max_uploads - record.used_count - record.reserved_count),
    }


async def verify_code(code: str):
    record = await DeliveryCode.filter(code_digest=code_digest(code)).first()
    if not record:
        raise HTTPException(403, "寄件码无效、已过期或已停用")
    record = await active_code(record.id)
    remaining = record.max_uploads - record.used_count - record.reserved_count
    # 已预占的分片会话允许重新验证后续传，新文件仍由 reserve_slot 拒绝超额。
    if remaining <= 0 and not await DeliveryFile.filter(delivery_id=record.id, status="pending", token__startswith="d_").exists():
        raise HTTPException(409, "可上传次数已耗尽或正在使用，请联系管理员")
    # 旧码无法离线还原；持有者成功验证时补存其原码，不修改口令或重新生成。
    if record.code_value is None:
        await DeliveryCode.filter(id=record.id, code_value__isnull=True).update(code_value=code)
    # 凭证仅含寄件 ID，不携带 is_admin、目标路径或下载口令。
    token = create_token({"purpose": "delivery", "delivery_id": record.id}, expires_in=TOKEN_TTL)
    return {
        "token": token, "expires_in": TOKEN_TTL, "name": record.name,
        "remaining": remaining, "expires_at": record.expires_at,
        "upload_size": settings.upload_size, "allowed_file_types": settings.allowed_file_types,
        "expire_style": settings.expire_style, "max_save_seconds": settings.max_save_seconds,
        "enable_chunk": settings.enable_chunk,
    }


async def reserve_slot(code_id: int):
    """数据库原子预占最后一次上传；不以进程内锁代替跨 worker 并发控制。"""
    async with in_transaction() as conn:
        now = await get_now()
        p = _sql_placeholders(2)
        count, _ = await conn.execute_query(
            f"UPDATE deliverycode SET reserved_count = reserved_count + 1 "
            f"WHERE id = {p[0]} AND expires_at > {p[1]} AND owner_id = 'admin' "
            "AND enabled = 1 AND deleted = 0 AND used_count + reserved_count < max_uploads",
            [code_id, now],
        )
        if count != 1:
            raise HTTPException(409, "寄件码已失效或没有剩余上传次数")
        code = await DeliveryCode.get(id=code_id).using_db(conn)
        return await DeliveryFile.create(
            delivery_id=code.id, owner_id="admin", token=uuid.uuid4().hex,
            file_path=code.target_path, storage_type=code.storage_type, using_db=conn,
        )


def stored_file(record):
    """显示名保留，磁盘/对象键使用唯一名称，禁止同名覆盖。"""
    prefix, suffix = os.path.splitext(record.filename)
    return StoredFile(file_path=record.file_path, uuid_file_name=record.stored_name, prefix=prefix, suffix=suffix)


async def store_upload(record, file, *, expire_style=None, expire_value=1):
    """继承类型与容量限制；只在落盘和记录事务都成功后扣减成功次数。"""
    # 传入过期策略即明确请求生成取件码；旧客户端未传策略时仍保持私有收件语义。
    if expire_style is not None:
        validate_expire_style(expire_style)
        await get_expire_info(expire_value, expire_style)
    await validate_upload_file(file)
    size = file.size
    if size is None:
        file.file.seek(0, 2)
        size = file.file.tell()
        await file.seek(0)
    if size > int(settings.upload_size):
        raise HTTPException(413, "文件大小超过站点限制")
    filename = await normalize_delivery_filename(file.filename)
    record.filename = filename
    record.stored_name = f"{record.token}_{filename}"
    record.size = size
    await reserve_storage("delivery:" + record.token, size, STALE_SECONDS)
    await record.save(update_fields=["filename", "stored_name", "size", "updated_at"])
    storage = await get_storage(record.storage_type)
    # shield 防止本地后台写线程被取消后仍写入已经关闭的临时文件。
    writing = asyncio.create_task(storage.save_file(file.file, f"{record.file_path}/{record.stored_name}", file.content_type))
    try:
        await asyncio.shield(writing)
    except asyncio.CancelledError:
        try:
            await writing
        except Exception:
            logger.warning("被取消的寄件写入失败 id=%s", record.id, exc_info=True)
        raise
    # 兼容接口仅负责构造分享字段，扣次和关联提交与普通上传共用同一事务。
    share_fields = None
    if expire_style is not None:
        expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
        share_fields = dict(code=code, size=size, expired_at=expired_at,
                            expired_count=expired_count, used_count=used_count)
    share = await commit_delivery(record, share_fields)
    result = {"name": filename, "size": size, "message": "投递成功"}
    if share is not None:
        result.update(code=share.code, expired_at=share.expired_at, expired_count=share.expired_count)
    return result


async def heartbeat(record):
    """有效传输定期续租，进程异常退出后遗留记录才会被回收。"""
    while True:
        await asyncio.sleep(30)
        changed = await DeliveryFile.filter(id=record.id, status__in=["pending", "finalizing"]).update(updated_at=await get_now())
        if not changed:
            return
        # 大文件慢速传输期间维持容量预留，避免 TTL 到期使其他上传超配额。
        await StorageReservation.filter(token__in=reservation_tokens(record.token)).update(
            expires_at=await get_now() + timedelta(seconds=STALE_SECONDS)
        )


async def abort_upload(record_id: int, *, stale_before=None):
    """先释放次数，再保留 cleanup 记录跟踪残留文件，清理成功后释放占用容量。"""
    async with in_transaction() as conn:
        query = DeliveryFile.filter(id=record_id, status__in=["pending", "finalizing"])
        if stale_before is not None:
            query = query.filter(updated_at__lt=stale_before)
        changed = await query.using_db(conn).update(status="cleanup", updated_at=await get_now())
        if changed:
            record = await DeliveryFile.get(id=record_id).using_db(conn)
            await DeliveryCode.filter(id=record.delivery_id, reserved_count__gt=0).using_db(conn).update(
                reserved_count=F("reserved_count") - 1
            )
            # 转为 cleanup 后由收件记录计费，统一释放所有上传预留。
            await StorageReservation.filter(token__in=reservation_tokens(record.token)).using_db(conn).delete()
    await clean_file(record_id)


async def clean_file(record_id):
    """实际文件删除成功后物理删除收件记录；失败时保留记录计费并重试。"""
    record = await DeliveryFile.filter(id=record_id, status="cleanup").first()
    if not record:
        return
    try:
        if record.stored_name:
            storage = await get_storage(record.storage_type)
            # 复用普通上传的会话时，临时分片也必须按寄件存储回收，失败保留记录重试。
            if record.token.startswith("d_"):
                await storage.clean_chunks(record.token, f"{record.file_path}/{record.stored_name}")
            await storage.delete_file(stored_file(record))
        if record.token.startswith("d_"):
            await UploadChunk.filter(upload_id=record.token).delete()
            await PresignUploadSession.filter(upload_id=record.token).delete()
            await StorageReservation.filter(token__in=reservation_tokens(record.token)).delete()
        # 与普通文件管理一致，清理成功后不保留已删除文件的历史空壳。
        await DeliveryFile.filter(id=record.id, status="cleanup").delete()
    except Exception:
        logger.warning("寄件文件清理失败，将自动重试 id=%s", record.id, exc_info=True)


async def cleanup_once():
    """有限批次回收崩溃残留，避免任务持有大量 ORM 对象。"""
    before = await get_now() - timedelta(seconds=STALE_SECONDS)
    for record in await DeliveryFile.filter(status__in=["pending", "finalizing"], updated_at__lt=before).limit(100):
        await abort_upload(record.id, stale_before=before)
    for record in await DeliveryFile.filter(status="cleanup").limit(100):
        await clean_file(record.id)
    # 分享创建成功后若分片回收失败，继续清理临时分片，不撤销已经生成的取件码。
    tokens = await UploadChunk.filter(chunk_index=-1, upload_id__startswith="d_").limit(100).values_list("upload_id", flat=True)
    for record in await DeliveryFile.filter(token__in=tokens, status="shared"):
        try:
            storage = await get_storage(record.storage_type)
            await storage.clean_chunks(record.token, f"{record.file_path}/{record.stored_name}")
            await UploadChunk.filter(upload_id=record.token).delete()
        except Exception:
            logger.warning("寄件分享临时分片清理失败 id=%s", record.id, exc_info=True)
    # 旧版本仅在物理清理成功后标记 deleted 并将大小归零，分批移除这些历史空壳。
    deleted_ids = await DeliveryFile.filter(status="deleted", size=0).limit(100).values_list("id", flat=True)
    if deleted_ids:
        await DeliveryFile.filter(id__in=deleted_ids, status="deleted", size=0).delete()


async def cleanup_loop():
    while True:
        try:
            await cleanup_once()
        except Exception:
            logger.warning("寄件清理任务异常，下轮继续", exc_info=True)
        await asyncio.sleep(60)


async def request_file_removal(record_id):
    """普通文件管理、寄件管理和过期清理共用撤销流程，容量始终只计算一次。"""
    async with in_transaction() as conn:
        record = await DeliveryFile.filter(id=record_id).using_db(conn).first()
        # 管理员删除与自动过期可能同时触发；已被另一流程清除时视为完成。
        if record is None:
            return
        if record.status in {"pending", "finalizing"}:
            raise HTTPException(409, "文件正在上传，请稍后再试")
        if record.share_id is not None:
            await FileCodes.filter(id=record.share_id).using_db(conn).delete()
            # 元数据清理由原文件服务管理；这里仅清除对应记录，不能触碰其他分享。
            await KeyValue.filter(key=f"admin_file_metadata:{record.share_id}").using_db(conn).delete()
        await DeliveryFile.filter(id=record_id, status__in=["stored", "shared"]).using_db(conn).update(
            status="cleanup", updated_at=await get_now()
        )
    await clean_file(record_id)



def reservation_tokens(token):
    """集中定义寄件会话的容量键，续租、提交和取消不会漏掉某一种上传方式。"""
    tokens = ["delivery:" + token]
    if token.startswith("d_"):
        tokens.extend(["chunk:" + token, "presign:" + token])
    return tokens


async def commit_delivery(record, share_fields=None):
    """统一提交寄件扣次；无分享字段时保留旧客户端的私有收件语义。"""
    async with in_transaction() as conn:
        changed = await DeliveryFile.filter(id=record.id, status__in=["pending", "finalizing"]).using_db(conn).update(
            status="shared" if share_fields is not None else "stored", updated_at=await get_now()
        )
        if changed != 1:
            raise HTTPException(409, "该上传已完成或已被清理")
        changed = await DeliveryCode.filter(
            id=record.delivery_id, enabled=True, deleted=False,
            expires_at__gt=await get_now(), reserved_count__gt=0,
        ).using_db(conn).update(reserved_count=F("reserved_count") - 1, used_count=F("used_count") + 1)
        if changed != 1:
            raise HTTPException(409, "寄件码在上传期间失效")
        share = None
        if share_fields is not None:
            fields = dict(share_fields)
            # 存储名保证唯一，显示名、文本分享和原取件规则保持不变。
            if "text" not in fields:
                fields["prefix"], fields["suffix"] = os.path.splitext(record.filename)
                fields["file_path"] = record.file_path
                fields["uuid_file_name"] = record.stored_name
            share = await FileCodes.create(using_db=conn, **fields)
            await DeliveryFile.filter(id=record.id).using_db(conn).update(share_id=share.id, size=share.size)
        await StorageReservation.filter(token__in=reservation_tokens(record.token)).using_db(conn).delete()
        return share



async def normalize_delivery_filename(file_name):
    """新旧上传统一清理显示名，并预留唯一前缀所需的文件系统字节空间。"""
    filename = await sanitize_filename((file_name or "file").replace("\\", "/").split("/")[-1])
    return filename.encode("utf-8")[:180].decode("utf-8", errors="ignore") or "file"
