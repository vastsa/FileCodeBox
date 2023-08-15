# @Time    : 2023/8/15 17:43
# @Author  : Lan
# @File    : depends.py
# @Software: PyCharm
from typing import Union

from fastapi import Header, HTTPException
from fastapi.requests import Request
from core.settings import settings


async def admin_required(authorization: Union[str, None] = Header(default=None), request: Request = None):
    if authorization != settings.admin_token:
        raise HTTPException(status_code=401, detail='未授权或授权校验失败')
    return True
