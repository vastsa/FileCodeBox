from pydantic import BaseModel


class SelectFileModel(BaseModel):
    code: str


from typing import Optional


class InitChunkUploadModel(BaseModel):
    file_name: str
    chunk_size: int = 5 * 1024 * 1024
    file_size: int
    file_hash: str
    content_type: Optional[str] = "application/octet-stream"


class CompleteUploadModel(BaseModel):
    expire_value: int
    expire_style: str
