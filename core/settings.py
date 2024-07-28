# @Time    : 2023/8/15 09:51
# @Author  : Lan
# @File    : settings.py
# @Software: PyCharm
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
data_root = BASE_DIR / 'data'

if not data_root.exists():
    data_root.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    'file_storage': 'local',
    'name': '文件快递柜 - FileCodeBox',
    'description': '开箱即用的文件快传系统',
    'notify_title': '系统通知',
    'notify_content': '欢迎使用 FileCodeBox，本程序开源于 <a href="https://github.com/vastsa/FileCodeBox" target="_blank">Github</a> ，欢迎Star和Fork。',
    'page_explain': '请勿上传或分享违法内容。根据《中华人民共和国网络安全法》、《中华人民共和国刑法》、《中华人民共和国治安管理处罚法》等相关规定。 传播或存储违法、违规内容，会受到相关处罚，严重者将承担刑事责任。本站坚决配合相关部门，确保网络内容的安全，和谐，打造绿色网络环境。',
    'keywords': 'FileCodeBox, 文件快递柜, 口令传送箱, 匿名口令分享文本, 文件',
    's3_access_key_id': '',
    's3_secret_access_key': '',
    's3_bucket_name': '',
    's3_endpoint_url': '',
    's3_region_name': 'auto',
    's3_signature_version': 's3v2',
    's3_hostname': '',
    's3_proxy': 0,
    'max_save_seconds': 0,
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
    'expireStyle': ['day', 'hour', 'minute', 'forever', 'count'],
    'uploadMinute': 1,
    'opacity': 0.9,
    'background': '',
    'uploadCount': 10,
    'errorMinute': 1,
    'errorCount': 1,
    'port': 12345,
    'showAdminAddr': 0,
    'robotsText': 'User-agent: *\nDisallow: /',
}


class Settings:
    def __init__(self, defaults=None):
        self.default_config = defaults or {}
        self.user_config = {}

    def __getattr__(self, attr):
        if attr in self.user_config:
            return self.user_config[attr]
        if attr in self.default_config:
            return self.default_config[attr]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{attr}'")

    def __setattr__(self, key, value):
        if key in ['default_config', 'user_config']:
            super().__setattr__(key, value)
        else:
            self.user_config[key] = value

    def items(self):
        return {**self.default_config, **self.user_config}.items()


settings = Settings(DEFAULT_CONFIG)
