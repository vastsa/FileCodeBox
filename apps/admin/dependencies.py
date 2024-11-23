# @Time    : 2023/8/15 17:43
# @Author  : Lan
# @File    : depends.py
# @Software: PyCharm
from fastapi import Header, HTTPException
from fastapi.requests import Request
from core.settings import settings
from apps.admin.services import FileService, ConfigService, LocalFileService


async def admin_required(authorization: str = Header(default=None), request: Request = None):
    is_admin = authorization.split(' ')[-1] if authorization else '' == str(settings.admin_token)
    if request.url.path.startswith('/share/'):
        if not settings.openUpload and not is_admin:
            raise HTTPException(status_code=403, detail='本站未开启游客上传，如需上传请先登录后台')
    else:
        if not is_admin:
            raise HTTPException(status_code=401, detail='未授权或授权校验失败')
    return is_admin


async def get_file_service():
    return FileService()


async def get_config_service():
    return ConfigService()


async def get_local_file_service():
    return LocalFileService()
