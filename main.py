# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import random

from fastapi import FastAPI, UploadFile, File, Form
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post('/share/text/')
async def share_text(text: str = Form(...), expireValue: int = Form(...), expireStyle: str = Form(...), targetType: str = Form(...)):
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
async def share_file(file: UploadFile = File(default=None)):
    return {
        'code': 200,
        'msg': 'success',
        'data': {
            'code': random.randint(100000, 999999),
            'text': '/share/{}'.format(random.randint(100000, 999999)),
            'name': file.filename,
        }
    }
