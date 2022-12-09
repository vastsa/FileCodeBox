import datetime

from sqlalchemy import create_engine, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Boolean, Column, Integer, String

engine = create_engine('sqlite:///database.db', connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Codes(Base):
    __tablename__ = 'codes'
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True)
    key = Column(String(30), unique=True, index=True)
    name = Column(String(500))
    size = Column(Integer)
    type = Column(String(20))
    text = Column(String(500))
    used = Column(Boolean, default=False)
    use_time = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
