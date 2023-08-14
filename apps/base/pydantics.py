from pydantic import BaseModel


class SelectFileModel(BaseModel):
    code: str
