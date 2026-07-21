# @Time    : 2023/8/15 17:43
# @Author  : Lan
# @File    : depends.py
# @Software: PyCharm
from fastapi import Header, HTTPException, Depends
from fastapi.requests import Request
import base64
import hmac
import json
import time
from core.settings import (
    ADMIN_SESSION_EXPIRE_DEFAULT,
    ADMIN_SESSION_EXPIRE_MAX,
    ADMIN_SESSION_EXPIRE_MIN,
    settings,
)
from apps.admin.services import FileService, ConfigService, LocalFileService


def _get_jwt_secret() -> bytes:
    secret = getattr(settings, "jwt_secret", "")
    if not secret:
        raise RuntimeError("JWT签名密钥未初始化")
    return secret.encode()


def get_admin_session_expire_seconds() -> int:
    try:
        expires_in = int(
            getattr(settings, "adminSessionExpire", ADMIN_SESSION_EXPIRE_DEFAULT)
        )
    except (TypeError, ValueError):
        return ADMIN_SESSION_EXPIRE_DEFAULT
    if (
        not ADMIN_SESSION_EXPIRE_MIN <= expires_in <= ADMIN_SESSION_EXPIRE_MAX
        or expires_in % ADMIN_SESSION_EXPIRE_MIN != 0
    ):
        return ADMIN_SESSION_EXPIRE_DEFAULT
    return expires_in


def create_token(data: dict, expires_in: int | None = None) -> str:
    """
    创建JWT token
    :param data: 数据负载
    :param expires_in: 过期时间(秒)
    """
    token_lifetime = (
        get_admin_session_expire_seconds() if expires_in is None else expires_in
    )
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {**data, "exp": int(time.time()) + token_lifetime},
            separators=(",", ":"),
        ).encode()
    ).decode().rstrip("=")

    signature = hmac.new(
        _get_jwt_secret(), f"{header}.{payload}".encode(), "sha256"
    ).digest()
    signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{header}.{payload}.{signature}"


def verify_token(token: str) -> dict:
    """
    验证JWT token
    :param token: JWT token
    :return: 解码后的数据
    """
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")

        # 验证签名
        expected_signature = hmac.new(
            _get_jwt_secret(),
            f"{header_b64}.{payload_b64}".encode(),
            "sha256",
        ).digest()
        expected_signature_b64 = (
            base64.urlsafe_b64encode(expected_signature).decode().rstrip("=")
        )

        if not hmac.compare_digest(signature_b64, expected_signature_b64):
            raise ValueError("无效的签名")

        # 解码payload（兼容历史标准 base64 与 urlsafe base64）
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        try:
            payload_bytes = base64.urlsafe_b64decode(padded)
        except Exception:
            payload_bytes = base64.b64decode(padded)
        payload = json.loads(payload_bytes)

        # 检查是否过期
        if payload.get("exp", 0) < time.time():
            raise ValueError("token已过期")

        return payload
    except Exception as e:
        raise ValueError(f"token验证失败: {str(e)}")


def _extract_bearer_token(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权或授权校验失败")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="未授权或授权校验失败")
    return token


def _require_admin_payload(authorization: str) -> dict:
    token = _extract_bearer_token(authorization)
    try:
        payload = verify_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if not payload.get("is_admin", False):
        raise HTTPException(status_code=401, detail="未授权或授权校验失败")
    return payload


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
    authorization: str = Header(default=None), request: Request = None
):
    """
    验证管理员权限
    """
    if request and (request.method, request.url.path) in ADMIN_PUBLIC_ENDPOINTS:
        return None
    return _require_admin_payload(authorization)


async def share_required_login(authorization: str = Header(default=None)):
    """
    验证分享上传权限
    
    当settings.openUpload为False时，要求用户必须登录并具有管理员权限
    当settings.openUpload为True时，允许游客上传
    
    :param authorization: 认证头信息
    :param request: 请求对象
    :return: 验证结果
    """
    if not settings.openUpload:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=403, detail="本站未开启游客上传，如需上传请先登录后台"
            )
        _require_admin_payload(authorization)

    return True


async def get_file_service():
    return FileService()


async def get_config_service():
    return ConfigService()


async def get_local_file_service():
    return LocalFileService()
