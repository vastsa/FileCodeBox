# @Time    : 2023/8/14 11:48
# @Author  : Lan
# @File    : response.py
# @Software: PyCharm
from typing import Generic, TypeVar

from pydantic.v1.generics import GenericModel

T = TypeVar('T')


class APIResponse(GenericModel, Generic[T]):
    code: int = 200
    message: str = 'ok'
    detail: T
