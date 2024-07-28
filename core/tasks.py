# @Time    : 2023/8/15 22:00
# @Author  : Lan
# @File    : tasks.py
# @Software: PyCharm
import asyncio

from tortoise.expressions import Q

from apps.base.models import FileCodes
from apps.base.utils import ip_limit
from core.settings import settings
from core.storage import FileStorageInterface, storages
from core.utils import get_now


async def delete_expire_files():
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    while True:
        try:
            await ip_limit['error'].remove_expired_ip()
            await ip_limit['upload'].remove_expired_ip()
            expire_data = await FileCodes.filter(Q(expired_at__lt=await get_now()) | Q(expired_count=0)).all()
            for exp in expire_data:
                await file_storage.delete_file(exp)
                await exp.delete()
        except Exception as e:
            print(e)
        finally:
            await asyncio.sleep(600)
