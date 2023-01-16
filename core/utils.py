import datetime
import random
import asyncio
from sqlalchemy import or_, select, delete
from sqlalchemy.ext.asyncio.session import AsyncSession
from .database import Codes, engine
from .depends import IPRateLimit
from .storage import STORAGE_ENGINE
from settings import settings

storage = STORAGE_ENGINE[settings.STORAGE_ENGINE]()

# 错误IP限制器
error_ip_limit = IPRateLimit(settings.ERROR_COUNT, settings.ERROR_MINUTE)
# 上传文件限制器
upload_ip_limit = IPRateLimit(settings.UPLOAD_COUNT, settings.UPLOAD_MINUTE)


async def delete_expire_files():
    while True:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            await error_ip_limit.remove_expired_ip()
            await upload_ip_limit.remove_expired_ip()
            query = select(Codes).where(or_(Codes.exp_time < datetime.datetime.now(), Codes.count == 0))
            exps = (await s.execute(query)).scalars().all()
            files = []
            exps_ids = []
            for exp in exps:
                if exp.type != "text":
                    files.append(exp.text)
                exps_ids.append(exp.id)
            await storage.delete_files(files)
            query = delete(Codes).where(Codes.id.in_(exps_ids))
            await s.execute(query)
            await s.commit()
        await asyncio.sleep(settings.DELETE_EXPIRE_FILES_INTERVAL * 60)


async def get_code(s: AsyncSession):
    code = random.randint(10000, 99999)
    while (await s.execute(select(Codes.id).where(Codes.code == code))).scalar():
        code = random.randint(10000, 99999)
    return str(code)
