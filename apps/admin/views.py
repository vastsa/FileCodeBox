# @Time    : 2023/8/14 14:38
# @Author  : Lan
# @File    : views.py
# @Software: PyCharm
from fastapi import APIRouter

admin_api = APIRouter(
    prefix='/admin',
    tags=['管理'],
)
