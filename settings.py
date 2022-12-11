from starlette.config import Config

config = Config(".env")

DEBUG = config('DEBUG', cast=bool, default=False)

DATABASE_URL = config('DATABASE_URL', cast=str, default="sqlite+aiosqlite:///database.db")

DATA_ROOT = config('DATA_ROOT', cast=str, default="./static")

STATIC_URL = config('STATIC_URL', cast=str, default="/static")

ERROR_COUNT = config('ERROR_COUNT', cast=int, default=5)

ERROR_MINUTE = config('ERROR_MINUTE', cast=int, default=10)

ADMIN_ADDRESS = config('ADMIN_ADDRESS', cast=str, default="admin")

ADMIN_PASSWORD = config('ADMIN_PASSWORD', cast=str, default="admin")

FILE_SIZE_LIMIT = config('FILE_SIZE_LIMIT', cast=int, default=10) * 1024 * 1024

TITLE = config('TITLE', cast=str, default="文件快递柜")

DESCRIPTION = config('DESCRIPTION', cast=str, default="FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件等文件")

KEYWORDS = config('KEYWORDS', cast=str, default="FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件等文件")
