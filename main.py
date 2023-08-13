# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import register_tortoise
from apps.base.views import share_api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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

app.include_router(
    share_api
)
