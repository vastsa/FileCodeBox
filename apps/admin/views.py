# @Time    : 2023/8/14 14:38
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
import datetime
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from apps.admin.services import FileService, ConfigService, LocalFileService
from apps.admin.dependencies import (
    admin_required,
    get_admin_session,
    get_file_service,
    get_config_service,
    get_local_file_service,
)
from apps.admin.schemas import (
    IDData,
    IDsData,
    BatchUpdateFileData,
    BatchFilePolicyActionData,
    FilePolicyActionData,
    FileMetadataData,
    FileViewPresetData,
    FileViewPresetDeleteData,
    ShareItem,
    DeleteItem,
    LoginData,
    UpdateFileData,
)
from core.response import APIResponse
from apps.base.models import FileCodes, KeyValue
from tortoise.expressions import Q
from tortoise.functions import Count, Sum
from apps.admin.dependencies import (
    create_token,
    get_admin_session_expire_seconds,
    verify_token,
)
from core.logger import logger
from core.settings import settings
from core.utils import get_now, hash_password, password_needs_rehash, verify_password
from apps.base.utils import ip_limit

admin_api = APIRouter(
    prefix="/admin", tags=["管理"], dependencies=[Depends(admin_required)]
)


def _pick_query_text(*values: Optional[str]) -> Optional[str]:
    for value in values:
        normalized_value = str(value or "").strip()
        if normalized_value:
            return normalized_value
    return None


@admin_api.post("/login")
async def login(data: LoginData, ip: str = Depends(ip_limit["login"])):
    # 登录失败计入 IP 频率限制，超过 login_count/login_minute 后暂时锁定
    if not verify_password(data.password, settings.admin_token):
        ip_limit["login"].add_ip(ip)
        raise HTTPException(status_code=401, detail="密码错误")

    # 透明重哈希：存量 sha256/明文口令在登录成功（已证明持有口令）时升级为 scrypt
    if password_needs_rehash(settings.admin_token):
        try:
            record = await KeyValue.filter(key="settings").first()
            if record:
                stored = dict(record.value or {})
                stored["admin_token"] = hash_password(data.password)
                record.value = stored
                await record.save()
                settings.admin_token = stored["admin_token"]
                logger.info("管理员口令已升级为 scrypt 哈希")
        except Exception:
            logger.warning("口令哈希升级失败，保持旧格式", exc_info=True)

    expires_in = get_admin_session_expire_seconds()
    token = create_token({"is_admin": True}, expires_in=expires_in)
    return APIResponse(
        detail={
            "id": "admin",
            "username": "admin",
            "token": token,
            "token_type": "Bearer",
            "expires_at": verify_token(token)["exp"],
            "expires_in": expires_in,
        }
    )


@admin_api.get("/verify")
async def verify_admin(session: dict = Depends(get_admin_session)):
    return APIResponse(detail=session)


@admin_api.post("/logout")
async def logout_admin():
    return APIResponse(detail={"ok": True})


async def build_dashboard_recent_file(file_code: FileCodes) -> dict:
    is_expired = await file_code.is_expired()
    return {
        "id": file_code.id,
        "code": file_code.code,
        "name": file_code.prefix + file_code.suffix,
        "suffix": file_code.suffix,
        "size": file_code.size,
        "text": file_code.text is not None,
        "expired_at": file_code.expired_at,
        "expired_count": file_code.expired_count,
        "used_count": file_code.used_count,
        "created_at": file_code.created_at,
        "is_expired": is_expired,
    }


def _expired_predicate(now: datetime.datetime) -> Q:
    """SQL version of FileCodes.is_expired:
    expired_at IS NOT NULL AND ((expired_count < 0 AND expired_at < now) OR expired_count = 0)
    """
    return Q(expired_at__isnull=False) & (
        Q(expired_count__lt=0, expired_at__lt=now) | Q(expired_count=0)
    )


async def _sum_size(queryset) -> int:
    rows = await queryset.annotate(total=Sum("size")).values("total")
    return rows[0]["total"] or 0


@admin_api.get("/dashboard")
async def dashboard(file_service: FileService = Depends(get_file_service)):
    sys_start = await KeyValue.filter(key="sys_start").first()
    now = await get_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - datetime.timedelta(days=1)
    yesterday_end = today_start - datetime.timedelta(microseconds=1)

    # 简单计数全部走 SQL 聚合，避免整表载入内存（D3）。
    # 健康摘要依赖逐行 rules engine（_build_file_status_insights），保留一次遍历。
    total_files = await FileCodes.all().count()
    expired_count = await FileCodes.filter(_expired_predicate(now)).count()
    all_size = await _sum_size(FileCodes.all())
    used_count = (
        await FileCodes.all().annotate(total=Sum("used_count")).values("total")
    )[0]["total"] or 0
    text_count = await FileCodes.filter(text__isnull=False).count()
    chunked_count = await FileCodes.filter(is_chunked=True).count()
    yesterday_count = await FileCodes.filter(
        created_at__gte=yesterday_start, created_at__lte=yesterday_end
    ).count()
    yesterday_size = await _sum_size(
        FileCodes.filter(created_at__gte=yesterday_start, created_at__lte=yesterday_end)
    )
    today_count = await FileCodes.filter(created_at__gte=today_start).count()
    today_size = await _sum_size(FileCodes.filter(created_at__gte=today_start))

    suffix_rows = (
        await FileCodes.filter(text__isnull=True)
        .annotate(count=Count("id"))
        .values("suffix", "count")
    )
    suffix_counter = Counter(
        {((row["suffix"] or "file") or "file"): row["count"] for row in suffix_rows}
    )

    recent_file_codes = await FileCodes.all().order_by("-created_at").limit(8)
    health_summary = await file_service.build_file_health_summary(
        await FileCodes.all(), now=now
    )
    recent_activities = await file_service.list_admin_activities(limit=8)
    return APIResponse(
        detail={
            "total_files": total_files,
            "storage_used": str(all_size),
            "sys_uptime": sys_start.value if sys_start else None,
            "yesterday_count": yesterday_count,
            "yesterday_size": str(yesterday_size),
            "today_count": today_count,
            "today_size": str(today_size),
            "active_count": total_files - expired_count,
            "expired_count": expired_count,
            "text_count": text_count,
            "file_count": total_files - text_count,
            "chunked_count": chunked_count,
            "used_count": used_count,
            "storage_backend": settings.file_storage,
            "upload_size_limit": settings.upload_size,
            "open_upload": settings.open_upload,
            "enable_chunk": settings.enable_chunk,
            "max_save_seconds": settings.max_save_seconds,
            **health_summary,
            "health_summary": health_summary,
            "top_suffixes": [
                {"suffix": suffix, "count": count}
                for suffix, count in suffix_counter.most_common(8)
            ],
            "recent_files": [
                await build_dashboard_recent_file(file_code)
                for file_code in recent_file_codes
            ],
            "recent_activities": recent_activities["activities"],
        }
    )


@admin_api.get("/activities")
async def admin_activities(
    limit: int = 20,
    action: Optional[str] = None,
    targetType: Optional[str] = None,
    target_type: Optional[str] = None,
    keyword: Optional[str] = None,
    file_service: FileService = Depends(get_file_service),
):
    result = await file_service.list_admin_activities(
        limit=limit,
        action=action,
        target_type=_pick_query_text(targetType, target_type),
        keyword=keyword,
    )
    return APIResponse(detail=result)


@admin_api.delete("/file/delete")
async def file_delete(
    data: IDData,
    file_service: FileService = Depends(get_file_service),
):
    await file_service.delete_file(data.id)
    return APIResponse()


async def batch_delete_files(
    data: IDsData,
    file_service: FileService,
):
    if not data.ids:
        raise HTTPException(status_code=400, detail="请选择要删除的文件")
    result = await file_service.delete_files(data.ids)
    return APIResponse(detail=result)


@admin_api.delete("/file/batch-delete")
async def file_batch_delete(
    data: IDsData,
    file_service: FileService = Depends(get_file_service),
):
    return await batch_delete_files(data, file_service)


@admin_api.post("/file/batch-delete")
async def file_batch_delete_post(
    data: IDsData,
    file_service: FileService = Depends(get_file_service),
):
    return await batch_delete_files(data, file_service)


async def batch_update_files(
    data: BatchUpdateFileData,
    file_service: FileService,
):
    if not data.ids:
        raise HTTPException(status_code=400, detail="请选择要更新的文件")

    update_data = {}
    fields_set = data.model_fields_set
    should_clear_expired_at = bool(data.clear_expired_at)

    if should_clear_expired_at:
        update_data["expired_at"] = None
        update_data["expired_count"] = -1
    elif "expired_at" in fields_set and data.expired_at != "":
        update_data["expired_at"] = data.expired_at

    if (
        not should_clear_expired_at
        and "expired_count" in fields_set
        and data.expired_count is not None
    ):
        update_data["expired_count"] = data.expired_count

    if not update_data:
        raise HTTPException(status_code=400, detail="请选择要更新的字段")

    result = await file_service.update_files(data.ids, update_data)
    return APIResponse(detail=result)


@admin_api.patch("/file/batch-update")
async def file_batch_update(
    data: BatchUpdateFileData,
    file_service: FileService = Depends(get_file_service),
):
    return await batch_update_files(data, file_service)


@admin_api.post("/file/batch-update")
async def file_batch_update_post(
    data: BatchUpdateFileData,
    file_service: FileService = Depends(get_file_service),
):
    return await batch_update_files(data, file_service)


async def apply_file_policy_action(
    data: FilePolicyActionData,
    file_service: FileService,
):
    download_limit = data.download_limit

    detail = await file_service.apply_file_policy_action(
        file_id=data.id,
        action=data.action,
        download_limit=download_limit,
    )
    return APIResponse(detail=detail)


@admin_api.patch("/file/policy-action")
async def file_policy_action(
    data: FilePolicyActionData,
    file_service: FileService = Depends(get_file_service),
):
    return await apply_file_policy_action(data, file_service)


@admin_api.post("/file/policy-action")
async def file_policy_action_post(
    data: FilePolicyActionData,
    file_service: FileService = Depends(get_file_service),
):
    return await apply_file_policy_action(data, file_service)


async def apply_batch_file_policy_action(
    data: BatchFilePolicyActionData,
    file_service: FileService,
):
    if not data.ids:
        raise HTTPException(status_code=400, detail="请选择要更新的文件")

    download_limit = data.download_limit

    result = await file_service.apply_files_policy_action(
        file_ids=data.ids,
        action=data.action,
        download_limit=download_limit,
    )
    return APIResponse(detail=result)


@admin_api.patch("/file/batch-policy-action")
async def file_batch_policy_action(
    data: BatchFilePolicyActionData,
    file_service: FileService = Depends(get_file_service),
):
    return await apply_batch_file_policy_action(data, file_service)


@admin_api.post("/file/batch-policy-action")
async def file_batch_policy_action_post(
    data: BatchFilePolicyActionData,
    file_service: FileService = Depends(get_file_service),
):
    return await apply_batch_file_policy_action(data, file_service)


@admin_api.get("/file/list")
async def file_list(
    page: int = 1,
    size: int = 10,
    keyword: str = "",
    status: str = "",
    type: str = "",
    health: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    file_service: FileService = Depends(get_file_service),
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    files, total, summary = await file_service.list_files(
        page,
        size,
        keyword,
        status=status,
        file_type=type,
        health=health,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return APIResponse(
        detail={
            "page": page,
            "size": size,
            "data": files,
            "total": total,
            "summary": summary,
        }
    )


@admin_api.get("/file/detail")
async def file_detail(
    id: int,
    file_service: FileService = Depends(get_file_service),
):
    detail = await file_service.get_file_detail(id)
    return APIResponse(detail=detail)


@admin_api.post("/file/detail")
async def file_detail_post(
    data: IDData,
    file_service: FileService = Depends(get_file_service),
):
    detail = await file_service.get_file_detail(data.id)
    return APIResponse(detail=detail)


async def update_file_metadata(
    data: FileMetadataData,
    file_service: FileService,
):
    fields_set = data.model_fields_set
    update_note = "note" in fields_set
    update_tags = "tags" in fields_set
    if not update_note and not update_tags:
        raise HTTPException(status_code=400, detail="请选择要更新的元数据")

    detail = await file_service.update_file_metadata(
        file_id=data.id,
        note=data.note,
        tags=data.tags,
        update_note=update_note,
        update_tags=update_tags,
    )
    return APIResponse(detail=detail)


@admin_api.patch("/file/metadata")
async def file_metadata(
    data: FileMetadataData,
    file_service: FileService = Depends(get_file_service),
):
    return await update_file_metadata(data, file_service)


@admin_api.post("/file/metadata")
async def file_metadata_post(
    data: FileMetadataData,
    file_service: FileService = Depends(get_file_service),
):
    return await update_file_metadata(data, file_service)


@admin_api.get("/file/view-presets")
async def file_view_presets(
    file_service: FileService = Depends(get_file_service),
):
    result = await file_service.list_file_view_presets()
    return APIResponse(detail=result)


async def save_file_view_preset(
    data: FileViewPresetData,
    file_service: FileService,
):
    filters = data.filters if data.filters is not None else data.params
    preset = await file_service.save_file_view_preset(
        preset_id=data.id,
        name=data.name,
        filters=filters or {},
    )
    return APIResponse(detail=preset)


@admin_api.post("/file/view-presets")
async def file_view_presets_save(
    data: FileViewPresetData,
    file_service: FileService = Depends(get_file_service),
):
    return await save_file_view_preset(data, file_service)


@admin_api.patch("/file/view-presets")
async def file_view_presets_patch(
    data: FileViewPresetData,
    file_service: FileService = Depends(get_file_service),
):
    return await save_file_view_preset(data, file_service)


async def delete_file_view_preset(
    data: FileViewPresetDeleteData,
    file_service: FileService,
):
    result = await file_service.delete_file_view_preset(data.id)
    return APIResponse(detail=result)


@admin_api.delete("/file/view-presets")
async def file_view_presets_delete(
    data: FileViewPresetDeleteData,
    file_service: FileService = Depends(get_file_service),
):
    return await delete_file_view_preset(data, file_service)


@admin_api.post("/file/view-presets/delete")
async def file_view_presets_delete_post(
    data: FileViewPresetDeleteData,
    file_service: FileService = Depends(get_file_service),
):
    return await delete_file_view_preset(data, file_service)


@admin_api.get("/config/get")
async def get_config(
    config_service: ConfigService = Depends(get_config_service),
):
    return APIResponse(detail=config_service.get_config())


@admin_api.patch("/config/update")
async def update_config(
    data: dict,
    config_service: ConfigService = Depends(get_config_service),
    file_service: FileService = Depends(get_file_service),
):
    data.pop("themes_choices", None)
    await config_service.update_config(data)
    await file_service.record_admin_activity(
        action="config.update",
        target_type="config",
        target_name="system",
        count=1,
        meta={"fields": sorted(data.keys())},
    )
    return APIResponse()


@admin_api.get("/file/download")
async def file_download(
    id: int,
    file_service: FileService = Depends(get_file_service),
):
    file_content = await file_service.download_file(id)
    return file_content


@admin_api.get("/file/preview")
async def file_preview(
    id: int,
    max_chars: int = 4000,
    file_service: FileService = Depends(get_file_service),
):
    preview = await file_service.preview_file(id, max_chars)
    return APIResponse(detail=preview)


@admin_api.get("/local/lists")
async def get_local_lists(
    local_file_service: LocalFileService = Depends(get_local_file_service),
):
    files = await local_file_service.list_files()
    return APIResponse(detail=files)


@admin_api.delete("/local/delete")
async def delete_local_file(
    item: DeleteItem,
    local_file_service: LocalFileService = Depends(get_local_file_service),
    file_service: FileService = Depends(get_file_service),
):
    result = await local_file_service.delete_file(item.filename)
    await file_service.record_admin_activity(
        action="local_file.delete",
        target_type="local_file",
        target_name=item.filename,
        count=1,
        meta={"success": bool(result)},
    )
    return APIResponse(detail=result)


@admin_api.post("/local/share")
async def share_local_file(
    item: ShareItem,
    file_service: FileService = Depends(get_file_service),
):
    share_info = await file_service.share_local_file(item)
    await file_service.record_admin_activity(
        action="local_file.share",
        target_type="file",
        target_id=share_info.get("id") if isinstance(share_info, dict) else None,
        target_name=item.filename,
        count=1,
        meta={
            "expire_value": item.expire_value,
            "expire_style": item.expire_style,
        },
    )
    return APIResponse(detail=share_info)


@admin_api.patch("/file/update")
async def update_file(
    data: UpdateFileData,
    file_service: FileService = Depends(get_file_service),
):
    await file_service.update_file(
        file_id=data.id,
        code=data.code,
        prefix=data.prefix,
        suffix=data.suffix,
        expired_at=data.expired_at,
        expired_count=data.expired_count,
    )
    return APIResponse(detail="更新成功")
