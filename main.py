# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise

from apps.base.depends import IPRateLimit
from apps.base.models import KeyValue
from apps.base.utils import ip_limit
from apps.base.views import share_api
from apps.admin.views import admin_api
from core.response import APIResponse
from core.settings import data_root, settings, BASE_DIR, DEFAULT_CONFIG
from core.tasks import delete_expire_files

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount('/assets', StaticFiles(directory='./fcb-fronted/dist/assets'), name="assets")

register_tortoise(
    app,
    generate_schemas=True,
    add_exception_handlers=True,
    config={
        'connections': {
            'default': f'sqlite://{data_root}/filecodebox.db'
        },
        'apps': {
            'models': {
                "models": ["apps.base.models"],
                'default_connection': 'default',
            }
        },
        "use_tz": False,
        "timezone": "Asia/Shanghai",
    }
)

app.include_router(share_api)
app.include_router(admin_api)


@app.on_event("startup")
async def startup_event():
    # 启动后台任务，不定时删除过期文件
    asyncio.create_task(delete_expire_files())
    # 读取用户配置
    user_config, created = await KeyValue.get_or_create(key='settings', defaults={'value': DEFAULT_CONFIG})
    settings.user_config = user_config.value
    ip_limit['error'].minutes = settings.errorMinute
    ip_limit['error'].count = settings.errorCount
    ip_limit['upload'].minutes = settings.uploadMinute
    ip_limit['upload'].count = settings.uploadCount


@app.get('/')
async def index():
    return HTMLResponse(
        content=open(BASE_DIR / 'fcb-fronted/dist/index.html', 'r', encoding='utf-8').read()
        .replace('{{title}}', str(settings.name))
        .replace('{{description}}', str(settings.description))
        .replace('{{keywords}}', str(settings.keywords))
        .replace('{{opacity}}', str(settings.opacity))
        .replace('{{background}}', str(settings.background))
        , media_type='text/html', headers={'Cache-Control': 'no-cache'})


@app.get('/robots.txt')
async def robots():
    return HTMLResponse(content=settings.robotsText, media_type='text/plain')


@app.post('/')
async def get_config():
    return APIResponse(detail={
        'explain': settings.page_explain,
        'uploadSize': settings.uploadSize,
        'expireStyle': settings.expireStyle,
        'openUpload': settings.openUpload,
        'notify_title': settings.notify_title,
        'notify_content': settings.notify_content,
        'show_admin_address': settings.showAdminAddr,
    })


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app='main:app', host="0.0.0.0", port=settings.port, reload=False, workers=1)
