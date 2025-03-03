# @Time    : 2023/8/14 14:38
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
import datetime

from fastapi import APIRouter, Depends, HTTPException
from apps.admin.services import FileService, ConfigService, LocalFileService
from apps.admin.dependencies import (
    admin_required,
    get_file_service,
    get_config_service,
    get_local_file_service,
)
from apps.admin.schemas import IDData, ShareItem, DeleteItem, LoginData, UpdateFileData
from core.response import APIResponse
from apps.base.models import FileCodes, KeyValue
from apps.admin.dependencies import create_token
from core.settings import settings

admin_api = APIRouter(prefix="/admin", tags=["管理"])


@admin_api.post("/login")
async def login(data: LoginData):
    # 验证管理员密码
    if data.password != settings.admin_token:
        raise HTTPException(status_code=401, detail="密码错误")

    # 生成包含管理员身份的token
    token = create_token({"is_admin": True})
    return APIResponse(detail={"token": token, "token_type": "Bearer"})


@admin_api.get("/dashboard")
async def dashboard(admin: bool = Depends(admin_required)):
    all_codes = await FileCodes.all()
    all_size = str(sum([code.size for code in all_codes]))
    sys_start = await KeyValue.filter(key="sys_start").first()
    # 获取当前日期时间
    now = datetime.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - datetime.timedelta(days=1)
    yesterday_end = today_start - datetime.timedelta(microseconds=1)
    # 统计昨天一整天的记录数（从昨天0点到23:59:59）
    yesterday_codes = FileCodes.filter(
        created_at__gte=yesterday_start, created_at__lte=yesterday_end
    )
    # 统计今天到现在的记录数（从今天0点到现在）
    today_codes = FileCodes.filter(created_at__gte=today_start)
    return APIResponse(
        detail={
            "totalFiles": len(all_codes),
            "storageUsed": all_size,
            "sysUptime": sys_start.value,
            "yesterdayCount": await yesterday_codes.count(),
            "yesterdaySize": str(sum([code.size for code in await yesterday_codes])),
            "todayCount": await today_codes.count(),
            "todaySize": str(sum([code.size for code in await today_codes])),
        }
    )


@admin_api.delete("/file/delete")
async def file_delete(
        data: IDData,
        file_service: FileService = Depends(get_file_service),
        admin: bool = Depends(admin_required),
):
    await file_service.delete_file(data.id)
    return APIResponse()


@admin_api.get("/file/list")
async def file_list(
        page: int = 1,
        size: int = 10,
        keyword: str = "",
        file_service: FileService = Depends(get_file_service),
        admin: bool = Depends(admin_required),
):
    files, total = await file_service.list_files(page, size, keyword)
    return APIResponse(
        detail={
            "page": page,
            "size": size,
            "data": files,
            "total": total,
        }
    )


@admin_api.get("/config/get")
async def get_config(
        config_service: ConfigService = Depends(get_config_service),
        admin: bool = Depends(admin_required),
):
    return APIResponse(detail=config_service.get_config())


@admin_api.patch("/config/update")
async def update_config(
        data: dict,
        config_service: ConfigService = Depends(get_config_service),
        admin: bool = Depends(admin_required),
):
    data.pop("themesChoices")
    await config_service.update_config(data)
    return APIResponse()


@admin_api.get("/file/download")
async def file_download(
        id: int,
        file_service: FileService = Depends(get_file_service),
        admin: bool = Depends(admin_required),
):
    file_content = await file_service.download_file(id)
    return file_content


@admin_api.get("/local/lists")
async def get_local_lists(
        local_file_service: LocalFileService = Depends(get_local_file_service),
        admin: bool = Depends(admin_required),
):
    files = await local_file_service.list_files()
    return APIResponse(detail=files)


@admin_api.delete("/local/delete")
async def delete_local_file(
        item: DeleteItem,
        local_file_service: LocalFileService = Depends(get_local_file_service),
        admin: bool = Depends(admin_required),
):
    result = await local_file_service.delete_file(item.filename)
    return APIResponse(detail=result)


@admin_api.post("/local/share")
async def share_local_file(
        item: ShareItem,
        file_service: FileService = Depends(get_file_service),
        admin: bool = Depends(admin_required),
):
    share_info = await file_service.share_local_file(item)
    return APIResponse(detail=share_info)


@admin_api.patch("/file/update")
async def update_file(
        data: UpdateFileData,
        admin: bool = Depends(admin_required),
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
    if data.expired_at is not None and data.expired_at != file_code.expired_at:
        update_data["expired_at"] = data.expired_at
    if data.expired_count is not None and data.expired_count != file_code.expired_count:
        update_data["expired_count"] = data.expired_count

    await file_code.update_from_dict(update_data).save()
    return APIResponse(detail="更新成功")
