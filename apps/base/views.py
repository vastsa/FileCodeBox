# @Time    : 2023/8/14 03:59
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
from fastapi import APIRouter, Form, UploadFile, File, Depends, HTTPException
from starlette.responses import FileResponse

from apps.admin.depends import admin_required
from apps.base.models import FileCodes
from apps.base.pydantics import SelectFileModel
from apps.base.utils import get_expire_info, get_file_path_name, error_ip_limit, upload_ip_limit
from core.response import APIResponse
from core.settings import settings
from core.storage import file_storage

share_api = APIRouter(
    prefix='/share',
    tags=['分享'],
)


@share_api.post('/text/', dependencies=[Depends(admin_required)])
async def share_text(text: str = Form(...), expire_value: int = Form(default=1, gt=0), expire_style: str = Form(default='day'), ip: str = Depends(upload_ip_limit)):
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
    upload_ip_limit.add_ip(ip)
    return APIResponse(detail={
        'code': code,
    })


@share_api.post('/file/', dependencies=[Depends(admin_required)])
async def share_file(expire_value: int = Form(default=1, gt=0), expire_style: str = Form(default='day'), file: UploadFile = File(...), ip: str = Depends(upload_ip_limit)):
    if file.size > settings.uploadSize:
        raise HTTPException(status_code=403, detail=f'文件大小超过限制，最大为{settings.uploadSize}字节')
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
    upload_ip_limit.add_ip(ip)
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
    file_code.expired_count -= 1
    await file_code.save()
    return APIResponse(detail={
        'code': file_code.code,
        'name': file_code.prefix + file_code.suffix,
        'size': file_code.size,
        'text': file_code.text if file_code.text is not None else await file_storage.get_file_url(file_code),
    })


@share_api.get('/download')
async def download_file(key: str, code: str, ip: str = Depends(error_ip_limit)):
    is_valid = await file_storage.get_select_token(code) == key
    if not is_valid:
        error_ip_limit.add_ip(ip)
    file_code = await FileCodes.filter(code=code).first()
    if not file_code:
        return APIResponse(code=404, detail='文件不存在')
    if file_code.text:
        return APIResponse(detail=file_code.text)
    else:
        file_path = file_storage.root_path / await file_code.get_file_path()
        if not file_path.exists():
            return APIResponse(code=404, detail='文件已过期删除')
        return FileResponse(file_path, filename=file_code.prefix + file_code.suffix)
