# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import asyncio
import re

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse, FileResponse
from tortoise.contrib.fastapi import register_tortoise

from apps.base.views import share_api
from apps.admin.views import admin_api
from core.settings import data_root, settings, BASE_DIR
from core.tasks import delete_expire_files
from core.utils import max_save_times_desc

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get('/assets/{file_path:path}')
async def assets(file_path: str):
    if settings.max_save_seconds > 0:
        if re.match(r'SendView-[\d|a-f|A-F]+\.js', file_path):
            with open(BASE_DIR / f'./fcb-fronted/dist/assets/{file_path}', 'r', encoding='utf-8') as f:
                # 删除永久保存选项
                content = f.read()
                content = content.replace('_(c,{label:e(r)("send.expireData.forever"),value:"forever"},null,8,["label"]),', '')
                return HTMLResponse(content=content, media_type='text/javascript')
        if re.match(r'index-[\d|a-f|A-F]+\.js', file_path):
            with open(BASE_DIR / f'./fcb-fronted/dist/assets/{file_path}', 'r', encoding='utf-8') as f:
                # 更改本文描述
                desc_zh, desc_en = await max_save_times_desc(settings.max_save_seconds)
                content = f.read()
                content = content.replace('天数<7', desc_zh)
                content = content.replace('Days <7', desc_en)
                return HTMLResponse(content=content, media_type='text/javascript')
    return FileResponse(f'./fcb-fronted/dist/assets/{file_path}')


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


@app.get('/')
async def index():
    return HTMLResponse(
        content=open(BASE_DIR / './fcb-fronted/dist/index.html', 'r', encoding='utf-8').read()
        .replace('{{title}}', str(settings.name))
        .replace('{{description}}', str(settings.description))
        .replace('{{keywords}}', str(settings.keywords))
        .replace('{{opacity}}', str(settings.opacity))
        .replace('{{background}}', str(settings.background))
        , media_type='text/html', headers={'Cache-Control': 'no-cache'})


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app='main:app', host="0.0.0.0", port=settings.port, reload=False, workers=1)
