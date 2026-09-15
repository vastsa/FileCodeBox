"""寄件参数校验，所有路径都相对于已配置的存储根目录。"""

import re
from datetime import datetime, timezone, timedelta
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateDeliveryCode(BaseModel):
    # 禁止静默接受 owner_id 等越权字段，未来多用户必须由服务端身份决定归属。
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(default="", max_length=64)
    storage_type: str = "local"
    target_path: str = Field(min_length=1, max_length=200)
    expires_at: datetime
    max_uploads: int = Field(default=1, ge=1, le=100000)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        if value and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value):
            raise ValueError("寄件码须为 8 至 64 位字母、数字、下划线或短横线")
        return value

    @field_validator("storage_type")
    @classmethod
    def validate_storage(cls, value):
        if value not in {"local", "s3", "webdav", "onedrive", "opendal"}:
            raise ValueError("不支持的存储类型")
        return value

    @field_validator("target_path")
    @classmethod
    def validate_path(cls, value):
        # 同时约束 POSIX、Windows 与 URL 语义，避免 WebDAV 二次解码或盘符逃逸。
        parts = value.split("/")
        if (PurePosixPath(value).is_absolute()
                or any(part in {"", ".", ".."} for part in parts)
                or not re.fullmatch(r"[\w ./-]+", value, re.UNICODE)
                or any(part.endswith((".", " ")) for part in parts)
                or any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", part) for part in parts)):
            raise ValueError("目标目录必须是根目录内的相对路径，如 inbox/project-a")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value):
        # 无时区的后台输入明确解释为北京时间，接口返回保留时区。
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone(timedelta(hours=8)))
        if value <= datetime.now(timezone.utc):
            raise ValueError("有效期必须晚于当前时间")
        return value


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
