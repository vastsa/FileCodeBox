"""上传鉴权依赖：只解析授权与会话归属，存储、扣次和清理由公共上传服务完成。"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Header, HTTPException, Request

from apps.admin.dependencies import share_required_login, verify_token
from apps.base.models import FileCodes, StorageReservation
from apps.base.upload_sessions import reserve_slot, heartbeat, abort_upload, commit_delivery, STALE_SECONDS
from apps.delivery.services import upload_identity, active_code
from core.settings import settings
from core.storage import storages
from core.utils import get_now


@dataclass
class UploadAccess:
    code_id: int | None = None
    auth_version: int = 1
    record: StorageReservation | None = None
    completed: FileCodes | None = None


async def authorize_upload(request: Request, authorization: str | None = Header(default=None)):
    """游客、管理员与寄件身份隔离，跨码或无凭证访问会话统一返回不存在。"""
    access = UploadAccess()
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = verify_token(authorization[7:])
        except ValueError:
            # 非寄件身份交回上游游客/管理员规则，不能改变游客开放时的普通上传行为。
            payload = {}
        if payload.get("purpose") == "delivery" and not payload.get("is_admin"):
            access.code_id = await upload_identity(authorization)
            access.auth_version = int(payload.get("delivery_version", 1))
    if access.code_id is None:
        await share_required_login(authorization)
    upload_id = request.path_params.get("upload_id")
    completion = any(part in request.url.path for part in ("/complete/", "/confirm/", "/proxy/"))
    if upload_id and upload_id.startswith("d_"):
        if access.code_id is None:
            raise HTTPException(404, "上传会话不存在")
        access.record = await StorageReservation.filter(token=upload_id, delivery_id=access.code_id).first()
        if access.record is None and completion:
            access.completed = await FileCodes.filter(upload_id=upload_id, delivery_id=access.code_id).first()
        if access.record is None and access.completed is None:
            raise HTTPException(404, "上传会话不存在")
        if access.record and (access.record.status != "pending" or access.record.auth_version != access.auth_version):
            raise HTTPException(409, "上传正在完成、清理或授权已修改")
    elif upload_id and access.code_id is not None:
        raise HTTPException(404, "上传会话不属于该寄件码")
    if access.code_id is not None and access.completed is None:
        await active_code(access.code_id)
    finalizing = bool(access.record and completion)
    if access.record:
        changed = await StorageReservation.filter(id=access.record.id, status="pending").update(
            status="finalizing" if finalizing else "pending",
            expires_at=await get_now() + timedelta(seconds=STALE_SECONDS),
        )
        if not changed:
            raise HTTPException(409, "上传状态已变化，请重试")
        if finalizing:
            access.record.status = "finalizing"
    task = asyncio.create_task(heartbeat(access)) if access.code_id is not None else None
    try:
        yield access
    except BaseException:
        if not upload_id and access.record:
            await asyncio.shield(abort_access(access))
        raise
    finally:
        if finalizing:
            await StorageReservation.filter(id=access.record.id, status="finalizing").update(status="pending")
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def prepare_upload(access, file_name, file_size, upload_id):
    """普通上传保持原路径；寄件只补充授权选定的目录与短期预留。"""
    if access is None or access.code_id is None:
        return upload_id, None
    access.record = await reserve_slot(access.code_id, access.auth_version, file_name, upload_id)
    return access.record.token, f"{access.record.file_path}/{access.record.stored_name}"


async def upload_storage(access=None):
    if access is not None and access.record is not None:
        return storages[access.record.storage_type]()
    return storages[settings.file_storage]()


async def create_upload_share(access=None, **fields):
    if access is None or access.record is None:
        # 普通文件保持上游行为，不记录公共存储快照。
        fields.pop("storage_type", None)
        return await FileCodes.create(**fields)
    return await commit_delivery(access.record, fields)


async def abort_access(access, *, cleanup_after=None):
    if access is not None and access.record is not None:
        await abort_upload(access.record.id, cleanup_after=cleanup_after)


async def completed_upload(access):
    """响应丢失后按成功文件的会话标识重试，不重复写文件或扣次。"""
    if access is None or access.completed is None:
        return None
    share = access.completed
    if await share.is_expired():
        raise HTTPException(410, "该上传的文件已过期")
    return {"code": share.code, "name": share.prefix + share.suffix}
