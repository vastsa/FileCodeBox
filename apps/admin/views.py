# @Time    : 2023/8/14 14:38
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
from fastapi import APIRouter

from apps.admin.pydantics import IDData
from apps.base.models import FileCodes
from core.response import APIResponse
from core.storage import file_storage

admin_api = APIRouter(
    prefix='/admin',
    tags=['管理'],
)


@admin_api.delete('/file/delete')
async def file_delete(data: IDData):
    file_code = await FileCodes.get(id=data.id)
    await file_storage.delete_file(file_code)
    await file_code.delete()
    return APIResponse()


@admin_api.get('/file/list')
async def file_list(page: int = 1, size: int = 10):
    data = await FileCodes.all().limit(size).offset((page - 1) * size)
    return APIResponse(detail={
        'page': page,
        'size': size,
        'data': data,
        'total': await FileCodes.all().count(),
    })
