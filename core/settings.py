# @Time    : 2023/8/15 09:51
# @Author  : Lan
# @File    : settings.py
# @Software: PyCharm
from pathlib import Path

data_root = Path('./data')
if not data_root.exists():
    data_root.mkdir(parents=True, exist_ok=True)
