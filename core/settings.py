# @Time    : 2023/8/15 09:51
# @Author  : Lan
# @File    : settings.py
# @Software: PyCharm
from pathlib import Path

ADMIN_SESSION_EXPIRE_DEFAULT = 30 * 24 * 60 * 60
ADMIN_SESSION_EXPIRE_MIN = 24 * 60 * 60
ADMIN_SESSION_EXPIRE_MAX = 365 * 24 * 60 * 60

BASE_DIR = Path(__file__).resolve().parent.parent
data_root = BASE_DIR / "data"

if not data_root.exists():
    data_root.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "file_storage": "local",
    "storage_path": "",
    "storage_limit": 0,
    "name": "文件快递柜 - FileCodeBox",
    "description": "开箱即用的文件快传系统",
    "notify_title": "系统通知",
    "notify_content": '欢迎使用 FileCodeBox，本程序开源于 <a href="https://github.com/vastsa/FileCodeBox" target="_blank">Github</a> ，欢迎Star和Fork。',
    "page_explain": "请勿上传或分享违法内容。根据《中华人民共和国网络安全法》、《中华人民共和国刑法》、《中华人民共和国治安管理处罚法》等相关规定。 传播或存储违法、违规内容，会受到相关处罚，严重者将承担刑事责任。本站坚决配合相关部门，确保网络内容的安全，和谐，打造绿色网络环境。",
    "keywords": "FileCodeBox, 文件快递柜, 口令传送箱, 匿名口令分享文本, 文件",
    "s3_access_key_id": "",
    "s3_secret_access_key": "",
    "s3_bucket_name": "",
    "s3_endpoint_url": "",
    "s3_region_name": "auto",
    "s3_signature_version": "s3v2",
    "s3_hostname": "",
    "s3_addressing_style": "auto",
    "s3_proxy": 0,
    "max_save_seconds": 0,
    "aws_session_token": "",
    "onedrive_domain": "",
    "onedrive_client_id": "",
    "onedrive_username": "",
    "onedrive_password": "",
    "onedrive_root_path": "filebox_storage",
    "onedrive_proxy": 0,
    "webdav_root_path": "filebox_storage",
    "webdav_proxy": 0,
    "admin_token": "",
    "jwt_secret": "",
    "admin_session_expire": ADMIN_SESSION_EXPIRE_DEFAULT,
    "open_upload": 1,
    "upload_size": 1024 * 1024 * 10,
    "allowed_file_types": ["*"],
    "expire_style": ["day", "hour", "minute", "forever", "count"],
    "code_generate_type": "secret",
    "upload_minute": 1,
    "enable_chunk": 0,
    "webdav_url": "",
    "webdav_password": "",
    "webdav_username": "",
    "opacity": 0.9,
    "background": "",
    "upload_count": 10,
    "themes_choices": [
        {
            "name": "2023",
            "key": "themes/2023",
            "author": "Lan",
            "version": "1.0",
        },
        {
            "name": "2024",
            "key": "themes/2024",
            "author": "Lan",
            "version": "1.0",
        },
    ],
    "themes_select": "themes/2024",
    "error_minute": 1,
    "error_count": 10,
    "login_count": 5,
    "login_minute": 15,
    "server_workers": 1,
    "server_host": "0.0.0.0",
    "server_port": 12345,
    "show_admin_addr": 0,
    "robots_text": "User-agent: *\nDisallow: /",
    "trusted_proxies": [],
    "chunk_expire_hours": 24,
    "opendal_scheme": "s3",
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
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{attr}'"
        )

    def __setattr__(self, key, value):
        if key in ["default_config", "user_config"]:
            super().__setattr__(key, value)
        else:
            self.user_config[key] = value

    def unknown_keys(self, config: dict) -> list[str]:
        """Keys in `config` that DEFAULT_CONFIG does not define.

        Unknown keys silently fall through __getattr__ and crash later at the
        usage site; callers (refresh_settings) surface them at load time.
        """
        return sorted(k for k in config if k not in self.default_config)

    def items(self):
        return {**self.default_config, **self.user_config}.items()


settings = Settings(DEFAULT_CONFIG)
