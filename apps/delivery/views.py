"""寄件 HTTP 边界：鉴权先于读取上传体，管理接口不接受寄件凭证。"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from starlette.datastructures import UploadFile
from pydantic import ValidationError

from apps.admin.dependencies import get_admin_session
from apps.base.dependencies import get_client_ip
from apps.base.models import DeliveryCode, DeliveryFile, FileCodes
from apps.base.pages import theme_has_delivery_ui
from apps.base.services import response_from_download
from apps.base.utils import ip_limit
from apps.delivery import services
from apps.delivery.schemas import BatchDeliveryCodes, CreateDeliveryCode, SetDeliveryEnabled, UpdateDeliveryCode, VerifyDeliveryCode, DeliveryShareOptions
from apps.delivery.storage import get_storage
from core.errors import StorageError
from core.logger import logger
from core.response import APIResponse
from core.settings import settings

def private_admin_response(response: Response):
    # 管理列表现在含口令原文，禁止浏览器或中间代理缓存响应。
    response.headers["Cache-Control"] = "no-store"


public_api = APIRouter(prefix="/api/delivery", tags=["寄件投递"])
admin_api = APIRouter(prefix="/admin/delivery", tags=["寄件管理"], dependencies=[Depends(get_admin_session), Depends(private_admin_response)])
pages = APIRouter()
STATIC = Path(__file__).parent / "static"


@public_api.post("/verify")
async def verify(data: VerifyDeliveryCode, request: Request):
    ip = get_client_ip(request)
    limiter = ip_limit["error"]
    if not limiter.check_ip(ip):
        raise HTTPException(429, "尝试次数过多，请稍后重试")
    try:
        result = await services.verify_code(data.code)
    except HTTPException:
        limiter.add_ip(ip)
        raise
    return APIResponse(detail=result)


@public_api.post("/upload")
async def upload(request: Request, authorization: str | None = Header(default=None)):
    code_id = await services.upload_identity(authorization)
    await services.active_code(code_id)
    ip = ip_limit["upload"](request)
    ip_limit["upload"].add_ip(ip)
    record = await services.reserve_slot(code_id)
    heartbeat = asyncio.create_task(services.heartbeat(record))
    try:
        # 手动读取 multipart，使无权限请求在磁盘缓冲之前被拒绝；流式计算真实请求体上限。
        limit = max(0, int(settings.upload_size)) + 1024 * 1024
        received = 0

        async def limited_receive():
            nonlocal received
            message = await request.receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, "上传请求超过站点大小限制")
            return message

        bounded = Request(request.scope, receive=limited_receive)
        async with bounded.form(max_files=1, max_fields=2) as form:
            file = form.get("file")
            if (not isinstance(file, UploadFile) or len(form.multi_items()) != len(form)
                    or set(form) - {"file", "expire_style", "expire_value"}):
                raise HTTPException(422, "请求只能包含一个文件及过期参数")
            options = {}
            if "expire_style" in form or "expire_value" in form:
                try:
                    options = DeliveryShareOptions.model_validate({
                        "expire_style": form.get("expire_style"), "expire_value": form.get("expire_value", 1)
                    }).model_dump()
                except ValidationError:
                    raise HTTPException(422, "请选择有效的过期方式和正整数期限") from None
            result = await services.store_upload(record, file, **options)
        return APIResponse(detail=result)
    except StorageError:
        # 存储错误可能含目标 URL 或远端信息，不向访客返回原始异常。
        logger.warning("寄件存储失败 id=%s", record.id, exc_info=True)
        raise HTTPException(503, "文件保存失败，请稍后重试或联系管理员") from None
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        # 无论 HTTP 异常、断线或写入失败，都释放未完成的次数并跟踪文件清理。
        await asyncio.shield(services.abort_upload(record.id))


@admin_api.get("/codes")
async def list_codes(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = "",
    status: str = "all", storage_type: str = "all", tag: str = "", sort_by: str = "created_at", sort_order: str = "desc",
):
    # 在切片前统一完成筛选排序，total 与当前查询条件下的项目数一致。
    items = await services.list_codes(keyword=keyword, status=status, storage_type=storage_type, tag=tag, sort_by=sort_by, sort_order=sort_order)
    start = (page - 1) * page_size
    return APIResponse(detail={"items": items[start:start + page_size], "total": len(items)})


@admin_api.post("/codes", status_code=201)
async def create(data: CreateDeliveryCode):
    return APIResponse(detail=await services.create_code(data))


@admin_api.patch("/codes/{code_id}")
async def toggle(code_id: int, data: SetDeliveryEnabled):
    changed = await DeliveryCode.filter(id=code_id, owner_id="admin", deleted=False).update(enabled=data.enabled)
    if not changed:
        raise HTTPException(404, "寄件码不存在或已删除")
    return APIResponse(detail=await services.code_summary(await DeliveryCode.get(id=code_id)))


@admin_api.delete("/codes/{code_id}")
async def delete_code(code_id: int):
    # 寄件码物理删除；收件记录保留存储映射，已生成的普通取件码继续独立有效。
    changed = await DeliveryCode.filter(id=code_id, owner_id="admin").delete()
    if not changed:
        raise HTTPException(404, "寄件码不存在")
    return APIResponse(detail={"message": "寄件码已删除，已收文件仍保留"})


@admin_api.get("/codes/{code_id}/files")
async def list_files(code_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), unshared_only: bool = False):
    if not await DeliveryCode.filter(id=code_id, owner_id="admin").exists():
        raise HTTPException(404, "寄件码不存在")
    query = DeliveryFile.filter(delivery_id=code_id, owner_id="admin").exclude(status="deleted")
    # 已生成分享的收件使用文件管理列表；兼容区仅保留私有收件和上传/清理中的记录。
    if unshared_only:
        query = query.exclude(status="shared")
    total = await query.count()
    items = await query.order_by("-id").offset((page - 1) * page_size).limit(page_size).values(
        "id", "filename", "size", "status", "storage_type", "created_at", "share_id"
    )
    # 使用当前分享信息，原后台修改取件码或有效期后这里同步显示。
    shares = await FileCodes.filter(id__in=[item["share_id"] for item in items if item["share_id"] is not None])
    by_id = {share.id: share for share in shares}
    for item in items:
        share = by_id.get(item["share_id"])
        item["retrieval_code"] = share.code if share else None
        item["expired_at"] = share.expired_at if share else None
        item["expired_count"] = share.expired_count if share else None
        if share is not None and await share.is_expired():
            item["status"] = "expired"
    return APIResponse(detail={"items": items, "total": total})


@admin_api.get("/files/{file_id}/download")
async def download(file_id: int):
    record = await DeliveryFile.filter(id=file_id, owner_id="admin", status__in=["stored", "shared"]).first()
    if not record:
        raise HTTPException(404, "收件文件不存在或尚未完成")
    # 文本寄件直接复用普通文本分享，不尝试从存储读取不存在的文件对象。
    if record.share_id is not None:
        share = await FileCodes.filter(id=record.share_id).first()
        if share is not None and share.text is not None:
            return Response(content=share.text, media_type="text/plain", headers={
                "Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="Text.txt"',
                "X-Content-Type-Options": "nosniff",
            })
    storage = await get_storage(record.storage_type)
    response = response_from_download(await storage.get_file_response(services.stored_file(record)))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@admin_api.delete("/files/{file_id}")
async def delete_file(file_id: int):
    record = await DeliveryFile.filter(id=file_id, owner_id="admin").first()
    if not record or record.status == "deleted":
        raise HTTPException(404, "收件文件不存在")
    if record.status in {"pending", "finalizing"}:
        raise HTTPException(409, "该文件正在上传，请先禁用寄件码并等待上传结束")
    await services.request_file_removal(file_id)
    # 文件和收件记录均删除才算完成；清理失败时记录仍在，后台会继续重试。
    if await DeliveryFile.filter(id=file_id).exists():
        raise HTTPException(503, "存储暂时不可用，已排队自动重试删除")
    return APIResponse(detail={"message": "文件已删除"})


def page_response(filename):
    """页面无外部依赖；禁缓存和同源 CSP 防止口令、管理员凭证泄露。"""
    return FileResponse(STATIC / filename, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    })


@pages.get("/delivery", include_in_schema=False)
@pages.get("/delivery/", include_in_schema=False)
async def delivery_page():
    # 旧地址继续可用，安装原生寄件主题后跳转至其 Vue 路由。
    if theme_has_delivery_ui():
        return RedirectResponse('/#/delivery', status_code=307)
    return page_response("delivery.html")


@pages.get("/delivery/admin", include_in_schema=False)
async def management_page():
    if theme_has_delivery_ui():
        return RedirectResponse('/#/admin/delivery', status_code=307)
    return page_response("admin.html")


@pages.get("/delivery-assets/{filename}", include_in_schema=False)
async def asset(filename: str):
    if filename not in {"delivery.css", "delivery.js", "admin.js", "common.js", "entry.js", "entry.css", "logo.svg"}:
        raise HTTPException(404, "资源不存在")
    return FileResponse(STATIC / filename, headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


@admin_api.put("/codes/{code_id}")
async def update_config(code_id: int, data: UpdateDeliveryCode):
    """管理员编辑配置，启停操作仍使用兼容的 PATCH 接口。"""
    return APIResponse(detail=await services.update_code(code_id, data))


@admin_api.post("/codes/batch")
async def batch_codes(data: BatchDeliveryCodes):
    """批量启停、删除或调整期限和额度，不修改其他寄件配置。"""
    return APIResponse(detail=await services.batch_codes(data))
