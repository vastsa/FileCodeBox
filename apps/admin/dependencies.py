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
from core.settings import settings
from apps.admin.services import FileService, ConfigService, LocalFileService


def create_token(data: dict, expires_in: int = 3600 * 24) -> str:
    """
    创建JWT token
    :param data: 数据负载
    :param expires_in: 过期时间(秒)
    """
    header = base64.b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).decode()
    payload = base64.b64encode(
        json.dumps({**data, "exp": int(time.time()) + expires_in}).encode()
    ).decode()

    signature = hmac.new(
        settings.admin_token.encode(), f"{header}.{payload}".encode(), "sha256"
    ).digest()
    signature = base64.b64encode(signature).decode()

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
            settings.admin_token.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            "sha256",
        ).digest()
        expected_signature_b64 = base64.b64encode(expected_signature).decode()

        if signature_b64 != expected_signature_b64:
            raise ValueError("无效的签名")

        # 解码payload
        payload = json.loads(base64.b64decode(payload_b64))

        # 检查是否过期
        if payload.get("exp", 0) < time.time():
            raise ValueError("token已过期")

        return payload
    except Exception as e:
        raise ValueError(f"token验证失败: {str(e)}")


async def admin_required(
    authorization: str = Header(default=None), request: Request = None
):
    """
    验证管理员权限
    """
    try:
        if not authorization or not authorization.startswith("Bearer "):
            is_admin = False
        else:
            try:
                token = authorization.split(" ")[1]
                payload = verify_token(token)
                is_admin = payload.get("is_admin", False)
            except ValueError as e:
                is_admin = False

        if request.url.path.startswith("/share/"):
            if not settings.openUpload and not is_admin:
                raise HTTPException(
                    status_code=403, detail="本站未开启游客上传，如需上传请先登录后台"
                )
        else:
            if not is_admin:
                raise HTTPException(status_code=401, detail="未授权或授权校验失败")
        return is_admin
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def share_required_login(
    authorization: str = Header(default=None), request: Request = None
):
    """
    验证分享上传权限
    
    当settings.openUpload为False时，要求用户必须登录并具有管理员权限
    当settings.openUpload为True时，允许游客上传
    
    :param authorization: 认证头信息
    :param request: 请求对象
    :return: 验证结果
    """
    if not settings.openUpload:
        try:
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=403, detail="本站未开启游客上传，如需上传请先登录后台"
                )
            
            token = authorization.split(" ")[1]
            try:
                payload = verify_token(token)
                if not payload.get("is_admin", False):
                    raise HTTPException(status_code=401, detail="未授权或授权校验失败")
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=401, detail="认证失败：" + str(e))

    return True


async def get_file_service():
    return FileService()


async def get_config_service():
    return ConfigService()


async def get_local_file_service():
    return LocalFileService()
