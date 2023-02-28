import datetime
import hashlib
import random
import asyncio
import string
import time

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


async def get_random_num():
    return random.randint(10000, 99999)


async def get_random_string():
    r_s = string.ascii_letters + string.digits
    return ''.join(random.choice(r_s) for _ in range(5)).upper()


async def get_code(s: AsyncSession, exp_style):
    if exp_style == 'forever':
        generate = get_random_string
    else:
        generate = get_random_num
    code = await generate()
    while (await s.execute(select(Codes.id).where(Codes.code == code))).scalar():
        code = await generate()
    return str(code)


async def get_token(ip, code):
    return hashlib.sha256(f"{ip}{code}{int(time.time() / 1000)}000{settings.ADMIN_PASSWORD}".encode()).hexdigest()


async def get_expire_info(expire_style, expire_value, s):
    now = datetime.datetime.now()
    if expire_value <= 0 or expire_value > 999:
        return True, None, None
    code = await get_code(s, expire_style)
    if expire_style == 'day':
        return False, now + datetime.timedelta(days=expire_value), -1, code
    elif expire_style == 'hour':
        return False, now + datetime.timedelta(hours=expire_value), -1, code
    elif expire_style == 'minute':
        return False, now + datetime.timedelta(minutes=expire_value), -1, code
    elif expire_style == 'forever':
        return False, None, -1, code
    elif expire_style == 'count':
        return False, None, expire_value, code
    else:
        return True, None, None
