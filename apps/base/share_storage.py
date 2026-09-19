"""寄件生成的普通分享使用原投递后端，避免全站存储切换后找错文件。"""

from apps.base.models import DeliveryFile
from core.settings import settings
from core.storage import storages


async def delivery_record(file_code):
    return await DeliveryFile.filter(share_id=file_code.id).first()


async def storage_for_share(file_code, fallback=None):
    record = await delivery_record(file_code)
    if record is not None:
        # 延迟导入以保持应用模块边界，沿用 OneDrive 的精确对象键适配。
        from apps.delivery.storage import get_storage
        return await get_storage(record.storage_type)
    # 普通文件优先使用创建时的后端快照，历史 NULL 才兼容旧行为。
    if file_code.storage_type:
        return storages[file_code.storage_type]()
    return fallback if fallback is not None else storages[settings.file_storage]()


async def storage_type_for_share(file_code) -> str | None:
    """返回详情页可展示的实际后端；历史普通文件无来源时明确标记未知。"""
    record = await delivery_record(file_code)
    if record is not None:
        return record.storage_type
    return file_code.storage_type


async def remove_delivery_share(file_code):
    """先撤销取件记录再清理文件；失败残留继续占用容量并交由后台重试。"""
    record = await delivery_record(file_code)
    if record is None:
        return False
    from apps.delivery.services import request_file_removal
    await request_file_removal(record.id)
    return True
