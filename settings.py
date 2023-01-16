from starlette.config import Config
import os
import shutil

# 配置文件.env
# 请将.env移动至data目录，方便docker部署
# 判断根目录下是否存在.env文件
if os.path.exists('.env'):
    # 将文件复制到data目录
    shutil.copy('.env', 'data/.env')

config = Config("data/.env")
# 是否开启DEBUG模式
DEBUG = config('DEBUG', cast=bool, default=False)
# 端口
PORT = config('PORT', cast=int, default=12345)
# Sqlite数据库文件
DATABASE_FILE = config('DATABASE_FILE', cast=str, default='data/database.db')
# Sqlite套接字
DATABASE_URL = config('DATABASE_URL', cast=str, default=f"sqlite+aiosqlite:///{DATABASE_FILE}")
# 数据存储文件夹，文件就不暴露在静态资源里面了
DATA_ROOT = './data/' + config('DATA_ROOT', cast=str, default=f"static")
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
# 上传限制分钟数
UPLOAD_MINUTE = config('UPLOAD_MINUTE', cast=int, default=1)
# 删除过期文件的间隔（分钟）
DELETE_EXPIRE_FILES_INTERVAL = config('DELETE_EXPIRE_FILES_INTERVAL', cast=int, default=10)
# 管理地址
ADMIN_ADDRESS = config('ADMIN_ADDRESS', cast=str, default="admin")
# 管理密码
ADMIN_PASSWORD = config('ADMIN_PASSWORD', cast=str, default="admin")
# 文件大小限制，默认10MB
FILE_SIZE_LIMIT = config('FILE_SIZE_LIMIT', cast=int, default=10) * 1024 * 1024
# 网站标题
TITLE = config('TITLE', cast=str, default="文件快递柜")
# 网站描述
DESCRIPTION = config('DESCRIPTION', cast=str, default="FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件等文件")
# 网站关键词
KEYWORDS = config('KEYWORDS', cast=str, default="FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件等文件")
# 存储引擎：['aliyunsystem','filesystem']
STORAGE_ENGINE = config('STORAGE_ENGINE', cast=str, default="filesystem")
# 如果使用阿里云OSS的话需要创建如下参数
# 阿里云账号AccessKey
KeyId = config('KeyId', cast=str, default="阿里云账号AccessKey")
# 阿里云账号AccessKeySecret
KeySecret = config('KeySecret', cast=str, default="阿里云账号AccessKeySecret")
# 阿里云OSS Bucket的地域节点
OSS_ENDPOINT = config('BUCKET_URL', cast=str, default="阿里云OSS Bucket的地域节点")
# 阿里云OSS Bucket的BucketName
BUCKET_NAME = config('BUCKET_NAME', cast=str, default="阿里云OSS Bucket的BucketName")
# 访问文件的读取时长（s）
ACCESSTIME = config('ACCESSTIME', cast=int, default=60)
