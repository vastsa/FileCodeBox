"""寄件参数校验，所有路径都相对于已配置的存储根目录。"""

import re
from datetime import datetime, timezone, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.base.metadata import normalize_metadata_note, normalize_metadata_tags
from core.path_validation import validate_storage_directory


class DeliveryCodeConfig(BaseModel):
    """创建和编辑共用配置校验，编辑请求不能改动口令或计数。"""
    # 禁止静默接受 owner_id 等越权字段，未来多用户必须由服务端身份决定归属。
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    # system 表示上传开始时跟随全站配置；旧记录的明确存储值继续保留。
    storage_type: str = "system"
    target_path: str = Field(default="", max_length=200)
    expires_at: datetime
    max_uploads: int = Field(default=1, ge=1, le=100000)

    @field_validator("storage_type")
    @classmethod
    def validate_storage(cls, value):
        # 配置入口与设置页保持一致；历史收件的存储驱动仍保留供读取和清理。
        if value not in {"system", "local", "s3", "webdav"}:
            raise ValueError("不支持的存储类型")
        return value

    @field_validator("target_path")
    @classmethod
    def validate_path(cls, value):
        # 目录校验与系统设置共用，避免同一路径在两个入口产生不同结果。
        return validate_storage_directory(value, allow_empty=True, max_length=200)

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value):
        # 无时区的后台输入明确解释为北京时间，接口返回保留时区。
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone(timedelta(hours=8)))
        if value <= datetime.now(timezone.utc):
            raise ValueError("有效期必须晚于当前时间")
        return value

    @model_validator(mode="after")
    def validate_storage_mode(self):
        # 跟随系统时不保存隐藏表单中残留的自定义目录。
        if self.storage_type == "system":
            self.target_path = ""
        elif not self.target_path:
            raise ValueError("自定义存储位置必须填写目标目录")
        return self


class CreateDeliveryCode(DeliveryCodeConfig):
    # 新建自定义寄件码最多 32 位；自动生成仍固定为 16 位。
    code: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        if value and not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", value):
            raise ValueError("寄件码须为 8 至 32 位字母、数字、下划线或短横线")
        return value

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: Any) -> str:
        # 与文件管理的备注规则相同：非文本值转文本并截断。
        return normalize_metadata_note(value)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        return normalize_metadata_tags(value)


class UpdateDeliveryCode(BaseModel):
    """编辑寄件码时只更新提交的字段，历史过期记录可单独维护备注。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    storage_type: str | None = None
    target_path: str | None = Field(default=None, max_length=200)
    expires_at: datetime | None = None
    max_uploads: int | None = Field(default=None, ge=1, le=100000)
    code: str = Field(default="", max_length=32)
    note: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None

    @field_validator("storage_type")
    @classmethod
    def validate_storage(cls, value):
        if value is not None and value not in {"system", "local", "s3", "webdav"}:
            raise ValueError("不支持的存储类型")
        return value

    @field_validator("target_path")
    @classmethod
    def validate_path(cls, value):
        return None if value is None else validate_storage_directory(value, allow_empty=True, max_length=200)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        if value and not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", value):
            raise ValueError("寄件码须为 8 至 32 位字母、数字、下划线或短横线")
        return value

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value):
        # 编辑时可省略旧的过期时间；新提交的无时区时间按北京时间处理。
        return value.replace(tzinfo=timezone(timedelta(hours=8))) if value and value.tzinfo is None else value

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value):
        return None if value is None else normalize_metadata_note(value)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        return None if value is None else normalize_metadata_tags(value)

    @model_validator(mode="after")
    def reject_explicit_null(self):
        # 可选字段表示可以省略，不能用 null 意外清空已有配置。
        forbidden = {"name", "storage_type", "target_path", "expires_at", "max_uploads", "note", "tags"}
        if any(field in self.model_fields_set and getattr(self, field) is None for field in forbidden):
            raise ValueError("编辑字段不能为 null；请省略不修改的字段")
        return self


class BatchDeliveryCodes(BaseModel):
    """批量管理只允许指定动作涉及的字段，防止整表配置被意外覆盖。"""

    model_config = ConfigDict(extra="forbid")
    ids: list[int] = Field(min_length=1, max_length=1000)
    action: str
    expires_at: datetime | None = None
    max_uploads: int | None = Field(default=None, ge=1, le=100000)

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value):
        # 批量期限与单条编辑使用相同的后台时间解释规则。
        return value.replace(tzinfo=timezone(timedelta(hours=8))) if value and value.tzinfo is None else value

    @model_validator(mode="after")
    def validate_batch(self):
        self.ids = list(dict.fromkeys(self.ids))
        if not self.ids:
            raise ValueError("请至少选择一个寄件码")
        if self.action not in {"enable", "disable", "delete", "update"}:
            raise ValueError("不支持的批量操作")
        if self.action == "update" and self.expires_at is None and self.max_uploads is None:
            raise ValueError("批量更新至少需要有效期或上传次数")
        if self.action != "update" and (self.expires_at is not None or self.max_uploads is not None):
            raise ValueError("该批量操作不接受有效期或上传次数")
        return self


class VerifyDeliveryCode(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=8, max_length=64)


class SetDeliveryEnabled(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class DeliveryShareOptions(BaseModel):
    """上传选择的过期策略仍受全站白名单和最长保存时间约束。"""
    expire_style: str = Field(min_length=1, max_length=20)
    expire_value: int = Field(default=1, ge=1, le=1000000)
