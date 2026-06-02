# @Time    : 2023/8/14 14:38
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
import datetime
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from apps.admin.services import FileService, ConfigService, LocalFileService
from apps.admin.dependencies import (
    admin_required,
    get_admin_session,
    get_file_service,
    get_config_service,
    get_local_file_service,
)
from apps.admin.schemas import IDData, IDsData, ShareItem, DeleteItem, LoginData, UpdateFileData
from core.response import APIResponse
from apps.base.models import FileCodes, KeyValue
from apps.admin.dependencies import create_token
from core.settings import settings
from core.utils import get_now, verify_password

admin_api = APIRouter(
    prefix="/admin", tags=["管理"], dependencies=[Depends(admin_required)]
)


@admin_api.post("/login")
async def login(data: LoginData):
    if not verify_password(data.password, settings.admin_token):
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_token({"is_admin": True})
    return APIResponse(detail={"token": token, "token_type": "Bearer"})


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
        "expiredAt": file_code.expired_at,
        "expiredCount": file_code.expired_count,
        "usedCount": file_code.used_count,
        "createdAt": file_code.created_at,
        "isExpired": is_expired,
    }


@admin_api.get("/dashboard")
async def dashboard():
    all_codes = await FileCodes.all()
    all_size = sum([code.size for code in all_codes])
    sys_start = await KeyValue.filter(key="sys_start").first()
    now = await get_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - datetime.timedelta(days=1)
    yesterday_end = today_start - datetime.timedelta(microseconds=1)
    yesterday_codes = FileCodes.filter(
        created_at__gte=yesterday_start, created_at__lte=yesterday_end
    )
    today_codes = FileCodes.filter(created_at__gte=today_start)
    yesterday_file_codes = await yesterday_codes
    today_file_codes = await today_codes
    expired_count = 0
    for file_code in all_codes:
        if await file_code.is_expired():
            expired_count += 1

    text_count = sum(1 for file_code in all_codes if file_code.text is not None)
    chunked_count = sum(1 for file_code in all_codes if file_code.is_chunked)
    used_count = sum([file_code.used_count for file_code in all_codes])
    suffix_counter = Counter(
        "Text" if file_code.text is not None else (file_code.suffix or "file")
        for file_code in all_codes
    )
    recent_file_codes = sorted(
        all_codes,
        key=lambda file_code: file_code.created_at.timestamp()
        if file_code.created_at
        else 0,
        reverse=True,
    )[:8]
    return APIResponse(
        detail={
            "totalFiles": len(all_codes),
            "storageUsed": str(all_size),
            "sysUptime": sys_start.value if sys_start else None,
            "yesterdayCount": len(yesterday_file_codes),
            "yesterdaySize": str(sum([code.size for code in yesterday_file_codes])),
            "todayCount": len(today_file_codes),
            "todaySize": str(sum([code.size for code in today_file_codes])),
            "activeCount": len(all_codes) - expired_count,
            "expiredCount": expired_count,
            "textCount": text_count,
            "fileCount": len(all_codes) - text_count,
            "chunkedCount": chunked_count,
            "usedCount": used_count,
            "storageBackend": settings.file_storage,
            "uploadSizeLimit": settings.uploadSize,
            "openUpload": settings.openUpload,
            "enableChunk": settings.enableChunk,
            "maxSaveSeconds": settings.max_save_seconds,
            "topSuffixes": [
                {"suffix": suffix, "count": count}
                for suffix, count in suffix_counter.most_common(8)
            ],
            "recentFiles": [
                await build_dashboard_recent_file(file_code)
                for file_code in recent_file_codes
            ],
        }
    )


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


@admin_api.get("/file/list")
async def file_list(
    page: int = 1,
    size: int = 10,
    keyword: str = "",
    status: str = "",
    type: str = "",
    sortBy: str = "created_at",
    sortOrder: str = "desc",
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
        sort_by=sortBy,
        sort_order=sortOrder,
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


@admin_api.get("/config/get")
async def get_config(
    config_service: ConfigService = Depends(get_config_service),
):
    return APIResponse(detail=config_service.get_config())


@admin_api.patch("/config/update")
async def update_config(
    data: dict,
    config_service: ConfigService = Depends(get_config_service),
):
    data.pop("themesChoices", None)
    await config_service.update_config(data)
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
    maxChars: int = 4000,
    file_service: FileService = Depends(get_file_service),
):
    preview = await file_service.preview_file(id, maxChars)
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
):
    result = await local_file_service.delete_file(item.filename)
    return APIResponse(detail=result)


@admin_api.post("/local/share")
async def share_local_file(
    item: ShareItem,
    file_service: FileService = Depends(get_file_service),
):
    share_info = await file_service.share_local_file(item)
    return APIResponse(detail=share_info)


@admin_api.patch("/file/update")
async def update_file(
    data: UpdateFileData,
):
    file_code = await FileCodes.filter(id=data.id).first()
    if not file_code:
        raise HTTPException(status_code=404, detail="文件不存在")
    update_data = {}

    if data.code is not None and data.code != file_code.code:
        # 判断code是否存在
        if await FileCodes.filter(code=data.code).first():
            raise HTTPException(status_code=400, detail="code已存在")
        update_data["code"] = data.code
    if data.prefix is not None and data.prefix != file_code.prefix:
        update_data["prefix"] = data.prefix
    if data.suffix is not None and data.suffix != file_code.suffix:
        update_data["suffix"] = data.suffix
    if (
        data.expired_at is not None
        and data.expired_at != ""
        and data.expired_at != file_code.expired_at
    ):
        update_data["expired_at"] = data.expired_at
    if data.expired_count is not None and data.expired_count != file_code.expired_count:
        update_data["expired_count"] = data.expired_count

    await file_code.update_from_dict(update_data).save()
    return APIResponse(detail="更新成功")
