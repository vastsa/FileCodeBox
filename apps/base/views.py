# @Time    : 2023/8/14 03:59
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
from fastapi import APIRouter, Form, UploadFile, File, Depends

from apps.base.models import FileCodes
from apps.base.pydantics import SelectFileModel
from apps.base.utils import get_expire_info, get_file_path_name, error_ip_limit
from core.response import APIResponse
from core.storage import file_storage

share_api = APIRouter(
    prefix='/share',
    tags=['分享'],
)


@share_api.post('/text/')
async def share_text(text: str = Form(...), expire_value: int = Form(default=1, gt=0), expire_style: str = Form(default='day')):
    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
    await FileCodes.create(
        code=code,
        text=text,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
        size=len(text),
        prefix='文本分享'
    )
    return APIResponse(detail={
        'code': code,
    })


@share_api.post('/file/')
async def share_file(expire_value: int = Form(default=1, gt=0), expire_style: str = Form(default='day'), file: UploadFile = File(...)):
    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
    path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(file)
    await file_storage.save_file(file, save_path)
    await FileCodes.create(
        code=code,
        prefix=prefix,
        suffix=suffix,
        uuid_file_name=uuid_file_name,
        file_path=path,
        size=file.size,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
    )
    return APIResponse(detail={
        'code': code,
        'name': file.filename,
    })


@share_api.post('/select/')
async def select_file(data: SelectFileModel, ip: str = Depends(error_ip_limit)):
    file_code = await FileCodes.filter(code=data.code).first()
    if not file_code:
        error_ip_limit.add_ip(ip)
        return APIResponse(code=404, detail='文件不存在')
    if await file_code.is_expired():
        return APIResponse(code=403, detail='文件已过期')
    file_code.used_count += 1
    await file_code.save()
    return APIResponse(detail={
        'code': file_code.code,
        'name': file_code.prefix + file_code.suffix,
        'size': file_code.size,
        'text': await file_storage.get_file_url(file_code),
    })
