"""寄件上传的短期预留：复用容量记录，成功文件只进入 FileCodes。"""

import asyncio
import os
from datetime import timedelta

from fastapi import HTTPException
from tortoise.expressions import F
from tortoise.transactions import in_transaction

from apps.base.models import DeliveryCode, FileCodes, StorageReservation, UploadChunk, PresignUploadSession
from apps.base.quota import _sql_placeholders
from apps.base.utils import build_file_path
from core.logger import logger
from core.settings import settings
from core.storage import StoredFile, storages
from core.utils import get_now

STALE_SECONDS = 7200


async def reserve_slot(code_id, version, file_name, upload_id):
    """次数原子预占与会话创建同事务；实际字节随后由共用配额入口预留。"""
    async with in_transaction() as conn:
        now = await get_now()
        p = _sql_placeholders(3)
        changed, _ = await conn.execute_query(
            f"UPDATE deliverycode SET reserved_count = reserved_count + 1 "
            f"WHERE id = {p[0]} AND expires_at > {p[1]} AND auth_version = {p[2]} "
            "AND enabled = 1 AND deleted = 0 AND used_count + reserved_count < max_uploads",
            [code_id, now, version],
        )
        if changed != 1:
            raise HTTPException(409, "寄件码已失效或没有剩余上传次数")
        # 每次新寄件都沿用原系统的存储设置和路径生成器，不读取寄件码独立配置。
        storage_type = settings.file_storage
        path, _, _, stored_name, _ = await build_file_path(file_name or "file", upload_id)
        token = "d_" + upload_id
        return await StorageReservation.create(
            token=token, size=0, delivery_id=code_id, auth_version=version,
            filename=stored_name, stored_name=stored_name,
            file_path=path, storage_type=storage_type,
            expires_at=now + timedelta(seconds=STALE_SECONDS), using_db=conn,
        )


async def heartbeat(access):
    """整个 HTTP 上传期间续租；后续分片请求重新启动租约，断线残留由定时清理回收。"""
    while True:
        await asyncio.sleep(30)
        if access.record is not None:
            await StorageReservation.filter(id=access.record.id, status__in=["pending", "finalizing"]).update(
                expires_at=await get_now() + timedelta(seconds=STALE_SECONDS)
            )


async def abort_upload(record_id, *, stale_before=None, cleanup_after=None):
    """只释放一次次数；清理失败的容量预留继续计费，防止失败残留绕过配额。"""
    async with in_transaction() as conn:
        query = StorageReservation.filter(id=record_id, delivery_id__isnull=False, status__in=["pending", "finalizing"])
        if stale_before is not None:
            query = query.filter(expires_at__lte=stale_before)
        changed = await query.using_db(conn).update(
            status="cleanup", expires_at=cleanup_after or await get_now()
        )
        if changed:
            record = await StorageReservation.get(id=record_id).using_db(conn)
            await DeliveryCode.filter(id=record.delivery_id, reserved_count__gt=0).using_db(conn).update(
                reserved_count=F("reserved_count") - 1
            )
    await clean_reservation(record_id)


async def clean_reservation(record_id):
    """物理对象清理成功后才删除预留；此表不保留任何已成功收件。"""
    record = await StorageReservation.filter(
        id=record_id, status="cleanup", delivery_id__isnull=False, expires_at__lte=await get_now()
    ).first()
    if record is None:
        return
    try:
        storage = storages[record.storage_type]()
        if record.stored_name:
            path = f"{record.file_path}/{record.stored_name}"
            await storage.clean_chunks(record.token, path)
            await storage.delete_file(StoredFile(file_path=record.file_path, uuid_file_name=record.stored_name))
        await UploadChunk.filter(upload_id=record.token).delete()
        await PresignUploadSession.filter(upload_id=record.token).delete()
        await record.delete()
    except Exception:
        logger.warning("上传残留清理失败，将重试 id=%s", record.id, exc_info=True)


async def commit_delivery(record, fields):
    """同事务扣次、建普通文件与释放容量；文件关联不再经过影子收件表。"""
    async with in_transaction() as conn:
        reserved = await StorageReservation.filter(id=record.id, status__in=["pending", "finalizing"]).using_db(conn).delete()
        if reserved != 1:
            raise HTTPException(409, "该上传已完成或正在清理")
        changed = await DeliveryCode.filter(
            id=record.delivery_id, auth_version=record.auth_version, enabled=True,
            deleted=False, expires_at__gt=await get_now(), reserved_count__gt=0,
        ).using_db(conn).update(reserved_count=F("reserved_count") - 1, used_count=F("used_count") + 1)
        if changed != 1:
            raise HTTPException(409, "寄件码在上传期间失效")
        fields.update(delivery_id=record.delivery_id, upload_id=record.token, storage_type=record.storage_type)
        if "text" not in fields:
            fields["prefix"], fields["suffix"] = os.path.splitext(record.filename)
            fields.update(file_path=record.file_path, uuid_file_name=record.stored_name)
        share = await FileCodes.create(using_db=conn, **fields)
        # 耗尽后保留授权历史和文件关联；管理员增加次数后可显式重新启用。
        await DeliveryCode.filter(id=record.delivery_id, reserved_count=0, used_count__gte=F("max_uploads")).using_db(conn).update(enabled=False)
        return share


async def cleanup_once():
    now = await get_now()
    for record in await StorageReservation.filter(delivery_id__isnull=False, status__in=["pending", "finalizing"], expires_at__lte=now).limit(100):
        await abort_upload(record.id, stale_before=now)
    for record in await StorageReservation.filter(delivery_id__isnull=False, status="cleanup", expires_at__lte=now).limit(100):
        await clean_reservation(record.id)
    # 成功后临时分片清理异常仍可按普通文件的 upload_id 重试，不保留影子文件行。
    tokens = await UploadChunk.filter(chunk_index=-1, upload_id__startswith="d_").limit(100).values_list("upload_id", flat=True)
    for share in await FileCodes.filter(upload_id__in=tokens):
        try:
            storage = storages[share.storage_type]()
            await storage.clean_chunks(share.upload_id, await share.get_file_path())
            await UploadChunk.filter(upload_id=share.upload_id).delete()
        except Exception:
            logger.warning("已完成上传的临时分片清理失败 id=%s", share.id, exc_info=True)


async def cleanup_loop():
    while True:
        try:
            await cleanup_once()
        except Exception:
            logger.warning("上传预留清理异常，下轮重试", exc_info=True)
        await asyncio.sleep(60)
