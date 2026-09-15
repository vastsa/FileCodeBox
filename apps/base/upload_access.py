"""普通上传的可选寄件授权层；通过显式参数传递，不修改全站配置或管理员会话。"""

import asyncio
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from apps.base.models import DeliveryFile, FileCodes
from core.settings import settings
from core.storage import storages
from core.utils import get_now


@dataclass
class UploadAccess:
    """每个请求独立的上传身份；寄件记录的 token 同时绑定普通上传会话。"""

    code_id: int | None = None
    record: DeliveryFile | None = None


async def authorize_upload(request: Request, authorization: str | None = Header(default=None)):
    """校验每一步的授权和会话归属，游客模式也不能访问寄件上传会话。"""
    from apps.admin.dependencies import share_required_login, verify_token
    from apps.delivery.services import active_code, heartbeat

    access = UploadAccess()
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = verify_token(authorization[7:])
        except ValueError:
            raise HTTPException(401, "上传凭证无效或已过期") from None
        if payload.get("purpose") == "delivery" and not payload.get("is_admin"):
            access.code_id = int(payload["delivery_id"])
    if access.code_id is None:
        await share_required_login(authorization)

    upload_id = request.path_params.get("upload_id")
    if upload_id:
        record = await DeliveryFile.filter(token=upload_id).first()
        if record is not None or upload_id.startswith("d_"):
            if record is None or record.delivery_id != access.code_id:
                raise HTTPException(404, "上传会话不存在")
            if record.status not in {"pending", "shared"}:
                raise HTTPException(409, "上传会话正在完成或清理，请稍后重试")
            access.record = record
        elif access.code_id is not None:
            raise HTTPException(404, "上传会话不属于该寄件码")

    completion_request = (
        "/complete/" in request.url.path or "/confirm/" in request.url.path or "/proxy/" in request.url.path
    )
    # 耗尽口令已被回收时，原凭证只可取回自己已完成会话的结果，不能启动或续传文件。
    completed_retry = completion_request and access.record is not None and access.record.status == "shared"
    if access.code_id is not None and not completed_retry:
        await active_code(access.code_id)

    # 完成阶段原子抢占，避免并发合并或代理上传覆盖同一个已发布文件。
    finalizing = False
    if access.record is not None and access.record.status == "pending" and completion_request:
        changed = await DeliveryFile.filter(id=access.record.id, status="pending").update(status="finalizing", updated_at=await get_now())
        if changed != 1:
            raise HTTPException(409, "上传正在完成，请稍后重试")
        access.record.status = "finalizing"
        finalizing = True
    # 长时间传输续租；新会话在初始化后由后续分片请求续租，空闲会话由后台回收。
    task = None
    if access.record is not None and access.record.status in {"pending", "finalizing"}:
        await DeliveryFile.filter(id=access.record.id).update(updated_at=await get_now())
        task = asyncio.create_task(heartbeat(access.record))
    try:
        yield access
    except BaseException:
        # 初始化、文本或单文件上传失败即释放本次占用；分片请求失败则保留已传内容供续传。
        if not upload_id and access.record is not None:
            await asyncio.shield(abort_access(access))
        raise
    finally:
        if finalizing:
            # 失败仍可重新提交完成请求；成功记录已变为 shared，不会被回退。
            await DeliveryFile.filter(id=access.record.id, status="finalizing").update(status="pending", updated_at=await get_now())
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def prepare_upload(access, file_name, file_size, upload_id):
    """仅寄件上传预占一次投递次数，并将目标存储和路径固定到上传会话。"""
    if access is None or access.code_id is None:
        return upload_id, None
    from apps.delivery.services import reserve_slot, normalize_delivery_filename

    record = await reserve_slot(access.code_id)
    # 先绑定记录，后续文件名处理或会话保存失败时依赖退出逻辑仍能释放占用。
    access.record = record
    name = await normalize_delivery_filename(file_name)
    record.token = "d_" + upload_id
    record.filename = name
    record.stored_name = record.token + "_" + name
    record.size = file_size
    await record.save()
    return record.token, f"{record.file_path}/{record.stored_name}"


async def upload_storage(access=None):
    """上传和合并均使用寄件码选定的存储，普通上传仍遵循全站设置。"""
    if access is not None and access.record is not None:
        from apps.delivery.storage import get_storage
        return await get_storage(access.record.storage_type)
    return storages[settings.file_storage]()


async def create_upload_share(access=None, **fields):
    """共用普通取件记录；寄件扣次与关联记录提交必须处于同一事务。"""
    if access is None or access.record is None:
        return await FileCodes.create(**fields)
    # 授权适配层只传递身份，扣次及私有/公开收件事务集中在寄件业务层。
    from apps.delivery.services import commit_delivery
    return await commit_delivery(access.record, fields)


async def abort_access(access):
    """取消或初始化失败释放寄件占用，实际残留交由原清理流程重试。"""
    if access is not None and access.record is not None:
        from apps.delivery.services import abort_upload
        await abort_upload(access.record.id)


async def completed_upload(access):
    """完成响应丢失后允许按原会话取回结果，不再合并、覆盖文件或重复扣次。"""
    if access is None or access.record is None or access.record.status != "shared":
        return None
    share = await FileCodes.filter(id=access.record.share_id).first()
    if share is None or await share.is_expired():
        raise HTTPException(410, "该上传的文件已过期")
    return {"code": share.code, "name": access.record.filename}
