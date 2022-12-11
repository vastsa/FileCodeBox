import datetime

from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession

engine = create_async_engine("sqlite+aiosqlite:///database.db")

Base = declarative_base()


async def get_session():
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


class Codes(Base):
    __tablename__ = "codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True)
    key = Column(String(30), unique=True, index=True)
    name = Column(String(500))
    size = Column(Integer)
    type = Column(String(20))
    text = Column(String(500))
    used = Column(Boolean, default=False)
    count = Column(Integer, default=-1)
    use_time = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    exp_time = Column(DateTime, nullable=True)
