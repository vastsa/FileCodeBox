"""寄件文件按授权后端定位；普通文件与 NAS 引用保持上游行为。"""

from apps.base.local_share import is_local_ref
from core.settings import settings
from core.storage import storages


async def storage_for_share(file_code, fallback=None):
    if file_code.delivery_id is not None and file_code.storage_type:
        # 只对寄件文件使用授权指定的后端，普通上传不采用旧快照列。
        return storages[file_code.storage_type]()
    return fallback if fallback is not None else storages[settings.file_storage]()


async def storage_type_for_share(file_code):
    """普通详情仍显示站点设置；NAS 引用及寄件按各自来源显示。"""
    if is_local_ref(file_code):
        return "local"
    return file_code.storage_type if file_code.delivery_id is not None else settings.file_storage
