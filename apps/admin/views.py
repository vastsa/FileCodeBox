# @Time    : 2023/8/14 14:38
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
import math

from fastapi import APIRouter, Depends

from apps.admin.depends import admin_required
from apps.admin.pydantics import IDData
from apps.base.models import FileCodes, KeyValue
from core.response import APIResponse
from core.settings import settings
from core.storage import FileStorageInterface, storages

admin_api = APIRouter(
    prefix='/admin',
    tags=['管理'],
)


@admin_api.post('/login', dependencies=[Depends(admin_required)])
async def login():
    return APIResponse()


@admin_api.delete('/file/delete', dependencies=[Depends(admin_required)])
async def file_delete(data: IDData):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    file_code = await FileCodes.get(id=data.id)
    await file_storage.delete_file(file_code)
    await file_code.delete()
    return APIResponse()


@admin_api.get('/file/list', dependencies=[Depends(admin_required)])
async def file_list(page: float = 1, size: int = 10):
    return APIResponse(detail={
        'page': page,
        'size': size,
        'data': await FileCodes.all().limit(size).offset((math.ceil(page) - 1) * size),
        'total': await FileCodes.all().count(),
    })


@admin_api.get('/config/get', dependencies=[Depends(admin_required)])
async def get_config():
    return APIResponse(detail=settings.items())


@admin_api.patch('/config/update', dependencies=[Depends(admin_required)])
async def update_config(data: dict):
    admin_token = data.get('admin_token')
    for key, value in data.items():
        if key not in settings.default_config:
            continue
        if key in ['errorCount', 'errorMinute', 'max_save_seconds', 'onedrive_proxy', 'openUpload', 'port', 's3_proxy', 'uploadCount', 'uploadMinute', 'uploadSize']:
            data[key] = int(value)
        elif key in ['opacity']:
            data[key] = float(value)
        else:
            data[key] = value
    if admin_token is None or admin_token == '':
        return APIResponse(code=400, detail='管理员密码不能为空')
    await KeyValue.filter(key='settings').update(value=data)
    for k, v in data.items():
        settings.__setattr__(k, v)
    return APIResponse()


# 根据code获取文件
async def get_file_by_id(id):
    # 查询文件
    file_code = await FileCodes.filter(id=id).first()
    # 检查文件是否存在
    if not file_code:
        return False, '文件不存在'
    return True, file_code


@admin_api.get('/file/download', dependencies=[Depends(admin_required)])
async def file_download(id: int):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    has, file_code = await get_file_by_id(id)
    # 检查文件是否存在
    if not has:
        # 返回API响应
        return APIResponse(code=404, detail='文件不存在')
    # 如果文件是文本，返回文本内容，否则返回文件响应
    if file_code.text:
        return APIResponse(detail=file_code.text)
    else:
        return await file_storage.get_file_response(file_code)
