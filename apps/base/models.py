# @Time    : 2023/8/13 20:43
# @Author  : Lan
# @File    : models.py
# @Software: PyCharm
from typing import Optional

from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator

from tortoise import fields, models
from datetime import datetime
from core.utils import get_now


class FileCodes(models.Model):
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=255, unique=True, index=True)
    prefix = fields.CharField(max_length=255, default="")
    suffix = fields.CharField(max_length=255, default="")
    uuid_file_name = fields.CharField(max_length=255, null=True)
    file_path = fields.CharField(max_length=255, null=True)
    size = fields.BigIntField(default=0)
    text = fields.TextField(null=True)
    expired_at = fields.DatetimeField(null=True)
    # -1 = 时间式（看 expired_at），<=0 的 0 = 次数耗尽。默认 -1 而非 0：
    # 0 语义是"次数已用完即过期"，忘传该字段的创建路径会得到立即过期的记录。
    expired_count = fields.IntField(default=-1)
    used_count = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    file_hash = fields.CharField(max_length=64, null=True)
    is_chunked = fields.BooleanField(default=False)
    upload_id = fields.CharField(max_length=36, null=True)
    # 普通文件创建时固定实际后端；历史记录没有可靠来源时保留 NULL。
    storage_type = fields.CharField(max_length=20, null=True)

    async def is_expired(self):
        if self.expired_at is None:
            return False
        if self.expired_at and self.expired_count < 0:
            return self.expired_at < await get_now()
        return self.expired_count <= 0

    async def get_file_path(self):
        return f"{self.file_path}/{self.uuid_file_name}"


class UploadChunk(models.Model):
    id = fields.IntField(pk=True)
    upload_id = fields.CharField(max_length=36, index=True)
    chunk_index = fields.IntField()
    chunk_hash = fields.CharField(max_length=64)
    total_chunks = fields.IntField()
    file_size = fields.BigIntField()
    chunk_size = fields.IntField()
    file_name = fields.CharField(max_length=255)
    save_path = fields.CharField(max_length=512, null=True)
    # 分片会话必须固定后端，避免全站设置切换后续传或清理到错误位置。
    storage_type = fields.CharField(max_length=20, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    completed = fields.BooleanField(default=False)


class KeyValue(Model):
    id: Optional[int] = fields.IntField(pk=True)
    key: Optional[str] = fields.CharField(
        max_length=255, description="键", index=True, unique=True
    )
    value: Optional[str] = fields.JSONField(description="值", null=True)
    created_at: Optional[datetime] = fields.DatetimeField(
        auto_now_add=True, description="创建时间"
    )


class PresignUploadSession(models.Model):
    """预签名上传会话模型"""

    id = fields.IntField(pk=True)
    upload_id = fields.CharField(max_length=36, unique=True, index=True)
    file_name = fields.CharField(max_length=255)
    file_size = fields.BigIntField()
    save_path = fields.CharField(max_length=512)
    # 直传 URL、代理上传和会话清理均使用初始化时确定的后端。
    storage_type = fields.CharField(max_length=20, null=True)
    mode = fields.CharField(max_length=10)  # "direct" 或 "proxy"
    expire_value = fields.IntField(default=1)
    expire_style = fields.CharField(max_length=20, default="day")
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField()  # 会话过期时间

    async def is_expired(self):
        """检查会话是否已过期"""
        return self.expires_at < await get_now()


class StorageReservation(models.Model):
    """尚未写入 FileCodes 的上传容量预留。"""

    id = fields.IntField(pk=True)
    token = fields.CharField(max_length=64, unique=True, index=True)
    size = fields.BigIntField()
    expires_at = fields.DatetimeField(index=True)


class DeliveryCode(models.Model):
    """只授予投递权限的口令；不进入公开取件码表，避免形成下载授权。"""

    id = fields.IntField(pk=True)
    code_digest = fields.CharField(max_length=64, unique=True)
    # 与普通取件码一样保留原文供管理员管理；旧记录为 NULL，不能从摘要反推。
    code_value = fields.CharField(max_length=64, null=True)
    # 改码时递增，令牌携带该版本后可立即撤销旧寄件授权。
    auth_version = fields.IntField(default=1)
    name = fields.CharField(max_length=100)
    note = fields.CharField(max_length=2000, default="")
    tags = fields.JSONField(default=list)
    owner_id = fields.CharField(max_length=64, default="admin", index=True)
    # system 仅标记寄件码跟随设置，实际收件记录始终保存解析后的存储类型与目录。
    storage_type = fields.CharField(max_length=20)
    target_path = fields.CharField(max_length=200)
    expires_at = fields.DatetimeField()
    max_uploads = fields.IntField()
    used_count = fields.IntField(default=0)
    reserved_count = fields.IntField(default=0)
    enabled = fields.BooleanField(default=True)
    deleted = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)


class DeliveryFile(models.Model):
    """寄件收件记录；pending 占用次数，stored 计入永久容量，独立于公开分享。"""

    id = fields.IntField(pk=True)
    delivery_id = fields.IntField(index=True)
    # 新的授权分享关联普通取件记录；NULL 表示旧版私有收件，绝不自动公开。
    share_id = fields.IntField(null=True, index=True)
    owner_id = fields.CharField(max_length=64, default="admin", index=True)
    token = fields.CharField(max_length=64, unique=True)
    filename = fields.CharField(max_length=255, default="")
    stored_name = fields.CharField(max_length=255, default="")
    # system 路径可包含 share/data 日期目录及唯一文件名，长度与普通文件路径对齐。
    file_path = fields.CharField(max_length=255)
    storage_type = fields.CharField(max_length=20)
    size = fields.BigIntField(default=0)
    status = fields.CharField(max_length=20, default="pending", index=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


file_codes_pydantic = pydantic_model_creator(FileCodes, name="FileCodes")
upload_chunk_pydantic = pydantic_model_creator(UploadChunk, name="UploadChunk")
key_value_pydantic = pydantic_model_creator(KeyValue, name="KeyValue")
presign_upload_session_pydantic = pydantic_model_creator(
    PresignUploadSession, name="PresignUploadSession"
)
