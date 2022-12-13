import datetime
import random
import asyncio
from sqlalchemy import or_, select, delete
from sqlalchemy.ext.asyncio.session import AsyncSession
import settings
from database import Codes, engine
from storage import STORAGE_ENGINE

storage = STORAGE_ENGINE[settings.STORAGE_ENGINE]()


async def delete_expire_files():
    while True:
        async with AsyncSession(engine, expire_on_commit=False) as s:
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
        await asyncio.sleep(random.randint(60, 300))


async def get_code(s: AsyncSession):
    code = random.randint(10000, 99999)
    while (await s.execute(select(Codes.id).where(Codes.code == code))).scalar():
        code = random.randint(10000, 99999)
    return str(code)
