# @Time    : 2023/8/13 19:54
# @Author  : Lan
# @File    : utils.py
# @Software: PyCharm
import datetime
import hashlib
import random
import string
import time

from apps.base.depends import IPRateLimit


async def get_random_num():
    """
    获取随机数
    :return:
    """
    return random.randint(10000, 99999)


r_s = string.ascii_uppercase + string.digits


async def get_random_string():
    """
    获取随机字符串
    :return:
    """
    return ''.join(random.choice(r_s) for _ in range(5))


async def get_now():
    """
    获取当前时间
    :return:
    """
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    )

async def get_select_token(code: int):
    """
    获取下载token
    :param code:
    :return:
    """
    token = "123456"
    return hashlib.sha256(f"{code}{int(time.time() / 1000)}000{token}".encode()).hexdigest()

async def get_file_url(code: int):
    """
    对于需要通过服务器中转下载的服务，获取文件下载地址
    :param code:
    :return:
    """
    return f'/share/download?key={await get_select_token(code)}&code={code}'