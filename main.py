# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise
from apps.base.views import share_api
from apps.admin.views import admin_api

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
            'default': 'sqlite://filecodebox.db'
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


@app.get('/')
async def index():
    return HTMLResponse(content=open('./fcb-fronted/dist/index.html', 'r', encoding='utf-8').read(), status_code=200)


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app='main:app', host="0.0.0.0", port=12345, reload=False, workers=3)
