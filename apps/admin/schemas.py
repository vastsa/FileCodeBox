from pydantic import BaseModel


class IDData(BaseModel):
    id: int


class ShareItem(BaseModel):
    expire_value: int
    expire_style: str = 'day'
    filename: str


class DeleteItem(BaseModel):
    filename: str


class LoginData(BaseModel):
    password: str
