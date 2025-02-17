# @Time    : 2023/8/13 20:43
# @Author  : Lan
# @File    : models.py
# @Software: PyCharm
from datetime import datetime
from typing import Optional

from tortoise import fields
from tortoise.models import Model
from tortoise.contrib.pydantic import pydantic_model_creator

from core.utils import get_now


class FileCodes(Model):
    id: Optional[int] = fields.IntField(pk=True)
    code: Optional[int] = fields.CharField(
        description="分享码", max_length=255, index=True, unique=True
    )
    prefix: Optional[str] = fields.CharField(
        max_length=255, description="前缀", default=""
    )
    suffix: Optional[str] = fields.CharField(
        max_length=255, description="后缀", default=""
    )
    uuid_file_name: Optional[str] = fields.CharField(
        max_length=255, description="uuid文件名", null=True
    )
    file_path: Optional[str] = fields.CharField(
        max_length=255, description="文件路径", null=True
    )
    size: Optional[int] = fields.IntField(description="文件大小", default=0)
    text: Optional[str] = fields.TextField(description="文本内容", null=True)
    expired_at: Optional[datetime] = fields.DatetimeField(
        null=True, description="过期时间"
    )
    expired_count: Optional[int] = fields.IntField(description="可用次数", default=0)
    used_count: Optional[int] = fields.IntField(description="已用次数", default=0)
    created_at: Optional[datetime] = fields.DatetimeField(
        auto_now_add=True, description="创建时间"
    )
    #
    # file_hash = fields.CharField(
    #     max_length=128,  # SHA-256需要64字符，这里预留扩展空间
    #     description="文件哈希值",
    #     unique=True,
    #     null=True  # 允许旧数据为空
    # )
    # hash_algorithm = fields.CharField(
    #     max_length=20,
    #     description="哈希算法类型",
    #     null=True,
    #     default="sha256"
    # )

    # # 新增分片字段
    # chunk_size = fields.IntField(
    #     description="分片大小(字节)",
    #     default=0
    # )
    # total_chunks = fields.IntField(
    #     description="总分片数",
    #     default=0
    # )
    # uploaded_chunks = fields.IntField(
    #     description="已上传分片数",
    #     default=0
    # )
    # upload_status = fields.CharField(
    #     max_length=20,
    #     description="上传状态",
    #     default="pending",  # pending/in_progress/completed
    #     choices=["pending", "in_progress", "completed"]
    # )
    # is_chunked = fields.BooleanField(
    #     description="是否分片上传",
    #     default=False
    # )

    async def is_expired(self):
        # 按时间
        if self.expired_at is None:
            return False
        if self.expired_at and self.expired_count < 0:
            return self.expired_at < await get_now()
        # 按次数
        else:
            return self.expired_count <= 0

    async def get_file_path(self):
        return f"{self.file_path}/{self.uuid_file_name}"


#
# class FileChunks(Model):
#     id = fields.IntField(pk=True)
#     file_code = fields.ForeignKeyField(
#         "models.FileCodes",
#         related_name="chunks",
#         on_delete=fields.CASCADE
#     )
#     chunk_number = fields.IntField(description="分片序号")
#     chunk_hash = fields.CharField(
#         max_length=128,
#         description="分片哈希校验值"
#     )
#     chunk_path = fields.CharField(
#         max_length=255,
#         description="分片存储路径"
#     )
#     created_at = fields.DatetimeField(
#         auto_now_add=True,
#         description="上传时间"
#     )
#
#     class Meta:
#         unique_together = [("file_code", "chunk_number")]


class KeyValue(Model):
    id: Optional[int] = fields.IntField(pk=True)
    key: Optional[str] = fields.CharField(
        max_length=255, description="键", index=True, unique=True
    )
    value: Optional[str] = fields.JSONField(description="值", null=True)
    created_at: Optional[datetime] = fields.DatetimeField(
        auto_now_add=True, description="创建时间"
    )


file_codes_pydantic = pydantic_model_creator(FileCodes, name="FileCodes")
