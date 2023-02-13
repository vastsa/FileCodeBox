import datetime

from sqlalchemy import Boolean, Column, Integer, String, DateTime, JSON, Text, select, insert, delete
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession

from settings import settings

engine = create_async_engine(settings.DATABASE_URL)
Base = declarative_base()


class Options(Base):
    __tablename__ = 'options'
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(JSON)


class Codes(Base):
    __tablename__ = "codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True)
    key = Column(String(30), unique=True)
    name = Column(String(500))
    size = Column(Integer)
    type = Column(String(20))
    text = Column(Text)
    used = Column(Boolean, default=False)
    count = Column(Integer, default=-1)
    use_time = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    exp_time = Column(DateTime, nullable=True)


async def init_models(s):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if await conn.scalar(select(Options).filter(Options.key == 'INSTALL')) is None:
            # 如果没有存在install，则清空表，并插入默认数据
            await conn.execute(delete(table=Options))
            await conn.execute(insert(table=Options, values=[
                {'key': 'INSTALL', 'value': settings.VERSION},
                {'key': 'DEBUG', 'value': settings.DEBUG},
                {'key': 'DATABASE_FILE', 'value': settings.DATABASE_FILE},
                {'key': 'PORT', 'value': settings.PORT},
                {'key': 'DATA_ROOT', 'value': settings.DATA_ROOT},
                {'key': 'STATIC_URL', 'value': settings.STATIC_URL},
                {'key': 'BANNERS', 'value': settings.BANNERS},
                {'key': 'ENABLE_UPLOAD', 'value': settings.ENABLE_UPLOAD},
                {'key': 'MAX_DAYS', 'value': settings.MAX_DAYS},
                {'key': 'ERROR_COUNT', 'value': settings.ERROR_COUNT},
                {'key': 'ERROR_MINUTE', 'value': settings.ERROR_COUNT},
                {'key': 'UPLOAD_COUNT', 'value': settings.UPLOAD_COUNT},
                {'key': 'UPLOAD_MINUTE', 'value': settings.UPLOAD_MINUTE},
                {'key': 'DELETE_EXPIRE_FILES_INTERVAL', 'value': settings.DELETE_EXPIRE_FILES_INTERVAL},
                {'key': 'ADMIN_ADDRESS', 'value': settings.ADMIN_ADDRESS},
                {'key': 'ADMIN_PASSWORD', 'value': settings.ADMIN_PASSWORD},
                {'key': 'FILE_SIZE_LIMIT', 'value': settings.FILE_SIZE_LIMIT},
                {'key': 'TITLE', 'value': settings.TITLE},
                {'key': 'DESCRIPTION', 'value': settings.DESCRIPTION},
                {'key': 'KEYWORDS', 'value': settings.KEYWORDS},
                {'key': 'STORAGE_ENGINE', 'value': settings.STORAGE_ENGINE},
                {'key': 'STORAGE_CONFIG', 'value': {}},
            ]))
            print(
                f'初始化数据库成功！\n'
                f'如您未配置.env文件，将为您随机生成信息\n'
                f'您的后台地址为：/{settings.ADMIN_ADDRESS}\n'
                f'您的管理员密码为：{settings.ADMIN_PASSWORD}\n'
                f'请尽快修改后台信息！\n'
                f'FileCodeBox https://github.com/vastsa/FileCodeBox'
            )
        await settings.updates(await conn.execute(select(Options).filter()))


async def get_config(key):
    async with engine.begin() as conn:
        return await conn.scalar(select(Options.value).filter(Options.key == key))


async def get_session():
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
