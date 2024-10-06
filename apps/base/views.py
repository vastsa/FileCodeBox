from fastapi import APIRouter, Form, UploadFile, File, Depends, HTTPException
from apps.admin.dependencies import admin_required
from apps.base.models import FileCodes
from apps.base.schemas import SelectFileModel
from apps.base.utils import get_expire_info, get_file_path_name, ip_limit
from core.response import APIResponse
from core.settings import settings
from core.storage import storages, FileStorageInterface
from core.utils import get_select_token

share_api = APIRouter(prefix='/share', tags=['分享'])


async def validate_file_size(file: UploadFile, max_size: int):
    if file.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise HTTPException(status_code=403, detail=f'大小超过限制,最大为{max_size_mb:.2f} MB')


async def create_file_code(code, **kwargs):
    return await FileCodes.create(code=code, **kwargs)


@share_api.post('/text/', dependencies=[Depends(admin_required)])
async def share_text(
        text: str = Form(...),
        expire_value: int = Form(default=1, gt=0),
        expire_style: str = Form(default='day'),
        ip: str = Depends(ip_limit['upload'])
):
    text_size = len(text.encode('utf-8'))
    max_txt_size = 222 * 1024
    if text_size > max_txt_size:
        raise HTTPException(status_code=403, detail='内容过多,建议采用文件形式')

    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
    await create_file_code(
        code=code,
        text=text,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
        size=len(text),
        prefix='文本分享'
    )
    ip_limit['upload'].add_ip(ip)
    return APIResponse(detail={'code': code})


@share_api.post('/file/', dependencies=[Depends(admin_required)])
async def share_file(
        expire_value: int = Form(default=1, gt=0),
        expire_style: str = Form(default='day'),
        file: UploadFile = File(...),
        ip: str = Depends(ip_limit['upload'])
):
    await validate_file_size(file, settings.uploadSize)

    if expire_style not in settings.expireStyle:
        raise HTTPException(status_code=400, detail='过期时间类型错误')

    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
    path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(file)

    file_storage: FileStorageInterface = storages[settings.file_storage]()
    await file_storage.save_file(file, save_path)

    await create_file_code(
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
    ip_limit['upload'].add_ip(ip)
    return APIResponse(detail={'code': code, 'name': file.filename})


async def get_code_file_by_code(code, check=True):
    file_code = await FileCodes.filter(code=code).first()
    if not file_code:
        return False, '文件不存在'
    if await file_code.is_expired() and check:
        return False, '文件已过期'
    return True, file_code


async def update_file_usage(file_code):
    file_code.used_count += 1
    if file_code.expired_count > 0:
        file_code.expired_count -= 1
    await file_code.save()


@share_api.get('/select/')
async def get_code_file(code: str, ip: str = Depends(ip_limit['error'])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    has, file_code = await get_code_file_by_code(code)
    if not has:
        ip_limit['error'].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    await update_file_usage(file_code)
    return await file_storage.get_file_response(file_code)


@share_api.post('/select/')
async def select_file(data: SelectFileModel, ip: str = Depends(ip_limit['error'])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    has, file_code = await get_code_file_by_code(data.code)
    if not has:
        ip_limit['error'].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    await update_file_usage(file_code)
    return APIResponse(detail={
        'code': file_code.code,
        'name': file_code.prefix + file_code.suffix,
        'size': file_code.size,
        'text': file_code.text if file_code.text is not None else await file_storage.get_file_url(file_code),
    })


@share_api.get('/download')
async def download_file(key: str, code: str, ip: str = Depends(ip_limit['error'])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    if await get_select_token(code) != key:
        ip_limit['error'].add_ip(ip)

    has, file_code = await get_code_file_by_code(code, False)
    if not has:
        return APIResponse(code=404, detail='文件不存在')

    return APIResponse(detail=file_code.text) if file_code.text else await file_storage.get_file_response(file_code)
