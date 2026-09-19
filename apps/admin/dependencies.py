# @Time    : 2023/8/15 17:43
# @Author  : Lan
# @File    : depends.py
# @Software: PyCharm

from fastapi import Header
from fastapi.requests import Request

from apps.admin.services import ConfigService, FileService, LocalFileService
from apps.base.auth import (
    _extract_bearer_token,
    _get_jwt_secret,
    _require_admin_payload,
    create_token,
    get_admin_session_expire_seconds,
    share_required_login,
    verify_token,
)

# 认证原语（JWT 创建/校验、Bearer 提取、分享上传门控）已下沉 apps.base.auth
# ——base 分享面与本模块共同消费，留在 base 避免 base→admin 反向依赖。
# 此处 re-export 保持既有 import 路径兼容（tests/admin.views 等）。

__all__ = [
    "_extract_bearer_token",
    "_get_jwt_secret",
    "_require_admin_payload",
    "ADMIN_PUBLIC_ENDPOINTS",
    "admin_required",
    "create_token",
    "get_admin_session",
    "get_admin_session_expire_seconds",
    "get_config_service",
    "get_file_service",
    "get_local_file_service",
    "share_required_login",
    "verify_token",
]


def get_admin_session(authorization: str = Header(default=None)) -> dict:
    token = _extract_bearer_token(authorization)
    payload = _require_admin_payload(authorization)
    return {
        "id": "admin",
        "username": "admin",
        "token": token,
        "token_type": "Bearer",
        "expires_at": payload.get("exp"),
    }


ADMIN_PUBLIC_ENDPOINTS = {("POST", "/admin/login")}


async def admin_required(
    authorization: str = Header(default=None),
    request: Request = None,  # type: ignore[assignment]  # FastAPI 运行时注入 Request；可选语义由下方 if request 判断
):
    """
    验证管理员权限
    """
    if request and (request.method, request.url.path) in ADMIN_PUBLIC_ENDPOINTS:
        return None
    return _require_admin_payload(authorization)


async def get_file_service():
    return FileService()


async def get_config_service():
    return ConfigService()


async def get_local_file_service():
    return LocalFileService()
