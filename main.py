# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import random

from fastapi import FastAPI, UploadFile, File, Form
from starlette.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import register_tortoise

from apps.base.models import FileCodes
from apps.base.utils import get_file_path_name, get_expire_info
from core.storage import file_storage

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


@app.post('/share/text/')
async def share_text(text: str = Form(...)):
    return {
        'code': 200,
        'msg': 'success',
        'data': {
            'code': random.randint(100000, 999999),
            'text': text,
            'name': '文本分享',
        }
    }


@app.post('/share/file/')
async def share_file(expire_value: int = Form(default=1, gt=0), expire_style: str = Form(default='day'), file: UploadFile = File(...)):
    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
    path, suffix, prefix, uuid_file_name, file_uuid, save_path = await get_file_path_name(file)
    await file_storage.save_file(file, save_path)
    file_code = await FileCodes.create(
        code=code,
        prefix=prefix,
        suffix=suffix,
        uuid_file_name=uuid_file_name,
        file_path=path,
        size=file.size,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
    )
    await file_storage.delete_file(file_code)
    return {
        'code': 200,
        'msg': 'success',
        'data': {
            'code': code,
            'text': '/share/{}'.format(random.randint(100000, 999999)),
            'name': file.filename,
        }
    }
