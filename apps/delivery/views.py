"""寄件只提供授权和后台配置，文件上传及管理复用普通文件接口。"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from tortoise.expressions import F

from apps.admin.dependencies import get_admin_session
from apps.base.dependencies import get_client_ip
from apps.base.models import DeliveryCode
from apps.base.pages import theme_has_delivery_ui
from apps.base.utils import ip_limit
from apps.delivery import services
from apps.delivery.schemas import BatchDeliveryCodes, CreateDeliveryCode, SetDeliveryEnabled, UpdateDeliveryCode, VerifyDeliveryCode
from core.response import APIResponse


def private_response(response: Response):
    # 授权响应和后台凭证都不得进入浏览器或中间代理缓存。
    response.headers["Cache-Control"] = "no-store"


public_api = APIRouter(prefix="/api/delivery", tags=["寄件授权"], dependencies=[Depends(private_response)])
admin_api = APIRouter(prefix="/admin/delivery", tags=["寄件管理"], dependencies=[Depends(get_admin_session), Depends(private_response)])
pages = APIRouter()


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


@public_api.post("/refresh")
async def refresh(authorization: str | None = Header(default=None)):
    """续期不使用管理员会话，也不会重新开放已撤销的寄件授权。"""
    return APIResponse(detail=await services.refresh_session(authorization))


@admin_api.get("/codes")
async def list_codes(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), keyword: str = "",
    status: str = "all", tag: str = "", sort_by: str = "created_at", sort_order: str = "desc",
):
    return APIResponse(detail=await services.list_codes(
        page=page, page_size=page_size, keyword=keyword, status=status,
        tag=tag, sort_by=sort_by, sort_order=sort_order,
    ))


@admin_api.post("/codes", status_code=201)
async def create(data: CreateDeliveryCode):
    return APIResponse(detail=await services.create_code(data))


@admin_api.patch("/codes/{code_id}")
async def toggle(code_id: int, data: SetDeliveryEnabled):
    # 缺少原文的历史码必须先重新设码，不能仅通过启用按钮恢复旧凭证。
    if data.enabled and await DeliveryCode.filter(id=code_id, deleted=False, code_value__isnull=True).exists():
        raise HTTPException(409, "请先编辑并重新设置寄件码，再启用授权")
    # 手动启停递增版本，停用后重新启用也不能复活旧令牌。
    changed = await DeliveryCode.filter(id=code_id, deleted=False).update(enabled=data.enabled, auth_version=F("auth_version") + 1)
    if not changed:
        raise HTTPException(404, "寄件码不存在或已删除")
    return APIResponse(detail=await services.code_summary(await DeliveryCode.get(id=code_id)))


@admin_api.delete("/codes/{code_id}")
async def delete_code(code_id: int):
    # 软删除保留收件关联；普通取件码生命周期独立，不撤销已完成文件。
    changed = await DeliveryCode.filter(id=code_id, deleted=False).update(deleted=True, enabled=False, auth_version=F("auth_version") + 1)
    if not changed:
        raise HTTPException(404, "寄件码不存在或已删除")
    return APIResponse(detail={"message": "寄件授权已撤销，已收文件仍保留"})


@admin_api.get("/codes/{code_id}/secret")
async def reveal_code(code_id: int):
    """只有管理员主动查看或复制时才读取口令，列表始终不携带凭证。"""
    record = await DeliveryCode.filter(id=code_id, deleted=False).first()
    if record is None:
        raise HTTPException(404, "寄件码不存在或已删除")
    return APIResponse(detail={"code": record.code_value})


@admin_api.put("/codes/{code_id}")
async def update_config(code_id: int, data: UpdateDeliveryCode):
    return APIResponse(detail=await services.update_code(code_id, data))


@admin_api.post("/codes/batch")
async def batch_codes(data: BatchDeliveryCodes):
    return APIResponse(detail=await services.batch_codes(data))


@pages.get("/delivery", include_in_schema=False)
@pages.get("/delivery/", include_in_schema=False)
async def delivery_page():
    if theme_has_delivery_ui():
        return RedirectResponse('/#/delivery', status_code=307)
    return upgrade_notice()


@pages.get("/delivery/admin", include_in_schema=False)
async def management_page():
    if theme_has_delivery_ui():
        return RedirectResponse('/#/admin/delivery', status_code=307)
    return upgrade_notice()


def upgrade_notice():
    """旧主题仅提示升级，不再注入脚本或维护第二套上传和管理界面。"""
    return PlainTextResponse("寄件功能需要支持寄件的 2024 主题，请联系管理员更新并切换主题。", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    })
