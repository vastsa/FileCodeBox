from pydantic import BaseModel


class SelectFileModel(BaseModel):
    code: str


class InitChunkUploadModel(BaseModel):
    file_name: str
    chunk_size: int = 5 * 1024 * 1024
    file_size: int
    file_hash: str


class CompleteUploadModel(BaseModel):
    expire_value: int
    expire_style: str
