# @Time    : 2023/8/13 20:43
# @Author  : Lan
# @File    : models.py
# @Software: PyCharm
from datetime import datetime
from typing import Optional

from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator


class FileCodes(Model):
    id: Optional[int] = fields.IntField(pk=True)
    code: Optional[int] = fields.CharField(description='分享码', max_length=255, index=True, unique=True)
    prefix: Optional[str] = fields.CharField(max_length=255, description='前缀', default='')
    suffix: Optional[str] = fields.CharField(max_length=255, description='后缀', default='')
    uuid_file_name: Optional[str] = fields.CharField(max_length=255, description='uuid文件名')
    file_path: Optional[str] = fields.CharField(max_length=255, description='文件路径')
    size: Optional[int] = fields.IntField(description='文件大小', default=0)

    expired_at: Optional[datetime] = fields.DatetimeField(null=True, description='过期时间')
    expired_count: Optional[int] = fields.IntField(description='可用次数', default=0)
    used_count: Optional[int] = fields.IntField(description='已用次数', default=0)

    created_at: Optional[datetime] = fields.DatetimeField(auto_now_add=True, description='创建时间')

    async def is_expired(self):
        if self.expired_at:
            return self.expired_at < datetime.now()
        else:
            return self.expired_count != -1 and self.used_count >= self.expired_count

    async def get_file_path(self):
        return f"{self.file_path}/{self.uuid_file_name}"


file_codes_pydantic = pydantic_model_creator(FileCodes, name='FileCodes')
