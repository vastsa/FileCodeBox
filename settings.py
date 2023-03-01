import uuid

from starlette.config import Config

# 配置文件.env，存放为data/.env
config = Config("data/.env")


class Settings:
    # 项目版本
    VERSION: str = config("VERSION", default="1.6")
    # 是否开启DEBUG模式
    DEBUG = config('DEBUG', cast=bool, default=False)
    # 端口
    PORT = config('PORT', cast=int, default=12345)
    # Sqlite数据库文件
    DATABASE_FILE = config('DATABASE_FILE', cast=str, default='data/database.db')
    # Sqlite套接字
    DATABASE_URL = config('DATABASE_URL', cast=str, default=f"sqlite+aiosqlite:///{DATABASE_FILE}")
    # 数据存储文件夹，文件就不暴露在静态资源里面了
    DATA_ROOT = config('DATA_ROOT', cast=str, default=f"./data/static")
    # 静态文件夹URL
    STATIC_URL = config('STATIC_URL', cast=str, default="/static")
    # 开启上传
    ENABLE_UPLOAD = config('ENABLE_UPLOAD', cast=bool, default=True)
    # 最长天数
    MAX_DAYS = config('MAX_DAYS', cast=int, default=7)
    # 错误次数
    ERROR_COUNT = config('ERROR_COUNT', cast=int, default=5)
    # 错误限制分钟数
    ERROR_MINUTE = config('ERROR_MINUTE', cast=int, default=10)
    # 上传次数
    UPLOAD_COUNT = config('UPLOAD_COUNT', cast=int, default=60)
    # 是否允许永久保存
    ENABLE_PERMANENT = config('ENABLE_PERMANENT', cast=bool, default=True)
    # 上传限制分钟数
    UPLOAD_MINUTE = config('UPLOAD_MINUTE', cast=int, default=1)
    # 删除过期文件的间隔（分钟）
    DELETE_EXPIRE_FILES_INTERVAL = config('DELETE_EXPIRE_FILES_INTERVAL', cast=int, default=10)
    # 管理地址
    ADMIN_ADDRESS = config('ADMIN_ADDRESS', cast=str, default=uuid.uuid4().hex)
    # 管理密码
    ADMIN_PASSWORD = config('ADMIN_PASSWORD', cast=str, default=uuid.uuid4().hex)
    # 文件大小限制，默认10MB
    FILE_SIZE_LIMIT = config('FILE_SIZE_LIMIT', cast=int, default=10 * 1024 * 1024)
    # 网站标题
    TITLE = config('TITLE', cast=str, default="文件快递柜")
    # 网站描述
    DESCRIPTION = config('DESCRIPTION', cast=str, default="FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件")
    # 网站关键词
    KEYWORDS = config('KEYWORDS', cast=str, default="FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件")
    # 存储引擎：['aliyunsystem','filesystem']
    STORAGE_ENGINE = config('STORAGE_ENGINE', cast=str, default="filesystem")
    # 存储引擎配置
    STORAGE_CONFIG = {}
    # Banners
    BANNERS = [{
        'text': 'FileCodeBox',
        'url': 'https://github.com/vastsa/FileCodeBox',
        'src': '/static/banners/img_1.png'
    }, {
        'text': 'LanBlog',
        'url': 'https://www.lanol.cn',
        'src': '/static/banners/img_2.png'
    }]
    int_dict = {'PORT', 'MAX_DAYS', 'ERROR_COUNT', 'ERROR_MINUTE', 'UPLOAD_COUNT', 'UPLOAD_MINUTE',
                'DELETE_EXPIRE_FILES_INTERVAL', 'FILE_SIZE_LIMIT'}
    bool_dict = {'DEBUG', 'ENABLE_UPLOAD'}

    async def update(self, key, value) -> None:
        if hasattr(self, key):
            if key in self.int_dict:
                value = int(value)
            elif key in self.bool_dict:
                value = bool(value)
            setattr(self, key, value)

    async def updates(self, options) -> None:
        with open('data/.env', 'w', encoding='utf-8') as f:
            for i, key, value in options:
                # 更新env文件
                f.write(f"{key}={value}\n")
                # 更新配置
                await self.update(key, value)
            f.flush()


settings = Settings()
