# @Time    : 2023/8/15 22:00
# @Author  : Lan
# @File    : tasks.py
# @Software: PyCharm
import asyncio

from tortoise.expressions import Q

from apps.base.models import FileCodes
from apps.base.utils import error_ip_limit, upload_ip_limit
from core.storage import file_storage
from core.utils import get_now


async def delete_expire_files():
    while True:
        try:
            await error_ip_limit.remove_expired_ip()
            await upload_ip_limit.remove_expired_ip()
            expire_data = await FileCodes.filter(Q(expired_at__lt=await get_now()) | Q(expired_count=0)).all()
            for exp in expire_data:
                await file_storage.delete_file(exp)
                await exp.delete()
        except Exception as e:
            print(e)
        finally:
            await asyncio.sleep(600)
