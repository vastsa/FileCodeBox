# @Time    : 2023/8/15 09:51
# @Author  : Lan
# @File    : settings.py
# @Software: PyCharm
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
data_root = BASE_DIR / 'data'
if not data_root.exists():
    data_root.mkdir(parents=True, exist_ok=True)
env_path = data_root / '.env2'
default_value = {
    'file_storage': 'local',
    'name': '文件快递柜-FileCodeBox',
    'description': '开箱即用的文件快传系统',
    'keywords': 'FileCodeBox, 文件快递柜, 口令传送箱, 匿名口令分享文本, 文件',
    'max_save_seconds': 0,
    's3_access_key_id': '',
    's3_secret_access_key': '',
    's3_bucket_name': '',
    's3_endpoint_url': '',
    's3_region_name': 'auto',
    's3_signature_version': 's3v2',
    's3_hostname': '',
    's3_proxy': 0,
    'aws_session_token': '',
    'onedrive_domain': '',
    'onedrive_client_id': '',
    'onedrive_username': '',
    'onedrive_password': '',
    'onedrive_root_path': 'filebox_storage',
    'onedrive_proxy': 0,
    'admin_token': 'FileCodeBox2023',
    'openUpload': 1,
    'uploadSize': 1024 * 1024 * 10,
    'uploadMinute': 1,
    'opacity': 0.9,
    'background': '',
    'uploadCount': 10,
    'errorMinute': 1,
    'errorCount': 1,
    'port': 12345,
}


class Settings:
    __instance = None

    def __init__(self):
        # 读取.env
        if not (env_path).exists():
            with open(env_path, 'w', encoding='utf-8') as f:
                for key, value in default_value.items():
                    f.write(f'{key}={value}\n')
        # 更新default_value
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                key, value = line.strip().split('=', maxsplit=1)
                # 将字符串转换为原本的类型
                if not key.startswith('opendal_') and isinstance(default_value[key], int):
                    value = int(value)
                default_value[key] = value

        # 更新self
        for key, value in default_value.items():
            self.__setattr__(key, value)

    def __new__(cls, *args, **kwargs):
        if not cls.__instance:
            cls.__instance = super(Settings, cls).__new__(cls, *args, **kwargs)
        return cls.__instance

    def __setattr__(self, key, value):
        if not key.startswith('opendal_') and type(value) == str and value.isnumeric():
            value = int(value)
        self.__dict__[key] = value
        with open(env_path, 'w', encoding='utf-8') as f:
            for key, value in self.__dict__.items():
                f.write(f'{key}={value}\n')

    def items(self):
        return self.__dict__.items()


settings = Settings()
