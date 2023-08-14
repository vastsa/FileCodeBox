# @Time    : 2023/8/13 19:54
# @Author  : Lan
# @File    : utils.py
# @Software: PyCharm
import datetime
import random
import string

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
