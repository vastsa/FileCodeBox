from pydantic import BaseModel, Field


class SelectFileModel(BaseModel):
    code: str


class InitChunkUploadModel(BaseModel):
    file_name: str
    # 在计算分片数之前限制非法或过大的分片，避免除零和单片内存失控。
    chunk_size: int = Field(default=5 * 1024 * 1024, ge=1, le=5 * 1024 * 1024)
    file_size: int = Field(ge=1)
    file_hash: str


class CompleteUploadModel(BaseModel):
    # 分享完成沿用正数期限，不能通过分片接口绕开表单约束。
    expire_value: int = Field(ge=1)
    expire_style: str


# 预签名上传相关模型
class PresignUploadInitRequest(BaseModel):
    """预签名上传初始化请求"""
    file_name: str
    file_size: int = Field(ge=1)
    expire_value: int = Field(default=1, ge=1)
    expire_style: str = "day"


class PresignUploadInitResponse(BaseModel):
    """预签名上传初始化响应"""
    upload_id: str
    upload_url: str
    mode: str  # "direct" 或 "proxy"
    save_path: str
    expires_in: int  # URL过期时间（秒）
